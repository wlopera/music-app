"""Tabla de archivos reutilizable (5 columnas Explorer, ordenable, filtrable)."""

import re
import struct
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import QByteArray, QMimeData, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from app import logs
from app.ui.models import COL_NOMBRE, FilterProxy, FileTableModel

logger = logs.get_logger("file_table")

_OLE_FNAME_W = 'application/x-qt-windows-mime;value="FileNameW"'
_OLE_FNAME = 'application/x-qt-windows-mime;value="FileName"'
_OLE_URL_W = 'application/x-qt-windows-mime;value="UniformResourceLocatorW"'
_OLE_URL_ANSI = 'application/x-qt-windows-mime;value="UniformResourceLocator"'
_QT_MODEL_DATALIST = "application/x-qabstractitemmodeldatalist"


def _qt_model_display_strings(mime_data) -> list[str]:
    """Extrae los DisplayRole (UTF-8) de un payload interno de Qt.

    Formato de QAbstractItemModel::encodeData por item:
      row(int32) col(int32) parentRow(int32) parentCol(int32)
      QHash<int, QByteArray>: count(uint32) { key(int32) len(uint32) bytes }
    DisplayRole == 0; el valor de un QString via QVariant::toByteArray() es UTF-8."""
    try:
        data = bytes(mime_data.data(_QT_MODEL_DATALIST))
    except Exception:
        return []
    strings: list[str] = []
    pos, n = 0, len(data)
    while pos + 16 <= n:
        row, col, prow, pcol = struct.unpack_from("<iiii", data, pos)
        pos += 16
        if pos + 4 > n:
            break
        count = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        for _ in range(count):
            if pos + 8 > n:
                return strings
            key, blen = struct.unpack_from("<iI", data, pos)
            pos += 8
            if pos + blen > n or blen > (1 << 20):
                return strings
            raw = data[pos:pos + blen]
            pos += blen
            if key == 0:
                try:
                    strings.append(raw.decode("utf-8", "replace"))
                except UnicodeDecodeError:
                    pass
    return strings


def _raw_paths(mime_data) -> list[str]:
    """Rutas crudas extraidas de los formatos de archivo de Windows/Explorer.

    En Windows Qt a veces entrega el drag sin .urls() parseado (hasUrls()==False)
    aunque el payload lleve archivos; estos formatos (text/uri-list, FileNameW,
    FileName, UniformResourceLocator*) rescatan las rutas."""
    out: list[str] = []

    def _add(piece: str) -> None:
        piece = piece.strip().strip("\x00").strip("\ufeff")
        if not piece:
            return
        if piece.lower().startswith("file://"):
            piece = unquote(urlparse(piece).path)
        if piece not in out:
            out.append(piece)

    try:
        uri_list = bytes(mime_data.data("text/uri-list")).decode("utf-8", "replace")
    except Exception:
        uri_list = ""
    for line in uri_list.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        _add(line)

    for fmt, enc, ansi in ((_OLE_FNAME_W, "utf-16-le", False),
                           (_OLE_FNAME, "cp1252", True),
                           (_OLE_URL_W, "utf-16-le", False),
                           (_OLE_URL_ANSI, "cp1252", True)):
        try:
            data = bytes(mime_data.data(fmt))
        except Exception:
            continue
        if not data:
            continue
        try:
            text = data.decode(enc, "replace") if not ansi else data.decode(enc, "replace")
        except UnicodeDecodeError:
            continue
        for piece in re.split(r"[\r\n\x00]+", text):
            if piece:
                _add(piece)
    return out


def file_paths_from_mime(mime_data) -> list[Path]:
    """Rutas locales que existen de verdad dentro de un payload de arrastre."""
    cands: list[Path] = []
    if mime_data is not None:
        for url in mime_data.urls():
            if url.isLocalFile():
                cands.append(Path(url.toLocalFile()))
        if not cands:
            cands = [Path(p) for p in _raw_paths(mime_data)]
        if not cands:
            cands = [Path(s) for s in _qt_model_display_strings(mime_data)]
    return [p for p in cands if p.is_file()]


def has_file_payload(mime_data) -> bool:
    """True si el payload parece llevar archivos aunque Qt no exponga .urls()."""
    if mime_data is None:
        return False
    if mime_data.hasUrls():
        return True
    if file_paths_from_mime(mime_data):
        return True
    return any(("FileName" in f or "uri-list" in f or "UniformResourceLocator" in f)
               for f in mime_data.formats())


def urls_from_mime(mime_data) -> list[Path]:
    return file_paths_from_mime(mime_data)


class FileTableView(QTableView):
    """QTableView con el modelo FileTableModel + filtro + orden por columnas."""

    clickedFile = pyqtSignal(Path)        # un clic sobre un archivo
    activatedFile = pyqtSignal(Path)      # doble clic / Enter
    selectionFilesChanged = pyqtSignal(list)
    contextMenuRequested = pyqtSignal(Path)  # None si clic derecho sobre zona vacia
    pathsDropped = pyqtSignal(list)       # rutas soltadas (si accept_file_drops=True)

    def __init__(self, extensions: list[str], sidecar_lookup=None, parent=None):
        super().__init__(parent)
        self.extensions = list(extensions)
        self.accept_file_drops = False
        self.model = FileTableModel(extensions, sidecar_lookup=sidecar_lookup, directory=None)
        self.proxy = FilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.setModel(self.proxy)

        self.setSortingEnabled(True)
        self.sortByColumn(COL_NOMBRE, Qt.SortOrder.AscendingOrder)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(32)
        hh = self.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setStretchLastSection(False)
        # Col 0 (Nombre) absorbe el espacio sobrante; las demas tienen ancho fijo
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, w in ((1, 148), (2, 148), (3, 52), (4, 80), (5, 190)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(col, w)

        self._click_guard = False
        self.doubleClicked.connect(self._on_double_clicked)
        self.clicked.connect(self._on_clicked)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    # --- Direccion / datos -------------------------------------------------------
    def set_directory(self, directory: Optional[Path]) -> None:
        # Limpia el filtro al cambiar de directorio
        if self.proxy.filterRegularExpression().pattern():
            self.set_filter("")
        self.model.set_directory(directory)
        self.sortByColumn(COL_NOMBRE, Qt.SortOrder.AscendingOrder)

    def set_filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)

    def set_extensions(self, extensions: list[str]) -> None:
        self.extensions = list(extensions)
        self.model.set_extensions(extensions)

    def set_sidecar_lookup(self, lookup) -> None:
        self.model.set_sidecar_lookup(lookup)

    def refresh(self) -> None:
        self.model.refresh()

    def selected_source_rows(self) -> list[int]:
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        src = self.model
        return [self.proxy.mapToSource(self.proxy.index(r, 0)).row() for r in rows]

    def selected_paths(self) -> list[Path]:
        src = self.model
        return [p for p in (src.path_at(r) for r in self.selected_source_rows()) if p]

    # --- Handlers internos ---------------------------------------------------------
    def _map_to_source(self, index) -> Optional[Path]:
        if not index.isValid():
            return None
        src_index = self.proxy.mapToSource(index)
        return self.model.path_at(src_index.row())

    def _on_clicked(self, index) -> None:
        path = self._map_to_source(index)
        if path is not None:
            self.clickedFile.emit(path)

    def _on_double_clicked(self, index) -> None:
        path = self._map_to_source(index)
        if path is not None:
            self.activatedFile.emit(path)

    def _on_selection_changed(self, *_args) -> None:
        self.selectionFilesChanged.emit(self.selected_paths())

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.contextMenuRequested.emit(None)
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.pos())
        path = self._map_to_source(index) if index.isValid() else None
        self.contextMenuRequested.emit(path)

    # --- Drag & drop (solo si accept_file_drops=True) ----------------------------
    def startDrag(self, actions) -> None:  # noqa: N802
        """Arrastre de la tabla como fuente: carga rutas reales (Explorer + Qt interno)."""
        paths = self.selected_paths()
        if not paths:
            return
        logger.info("tabla: startDrag con %d archivo(s)", len(paths))
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
        uri_list = "".join(f"file:///{str(p).replace(chr(92), '/')}\r\n" for p in paths)
        mime.setData("text/uri-list", QByteArray(uri_list.encode("utf-8")))
        joined = "\x00".join(str(p) for p in paths) + "\x00"
        mime.setData(_OLE_FNAME_W, QByteArray(joined.encode("utf-16-le")))
        mime.setData(_OLE_FNAME, QByteArray(joined.encode("cp1252", "replace")))
        drag.setMimeData(mime)
        drag.exec(actions, Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if self.accept_file_drops and has_file_payload(event.mimeData()):
            logger.debug("dragEnter tabla aceptado (%d archivo(s))",
                         len(file_paths_from_mime(event.mimeData())))
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if self.accept_file_drops and has_file_payload(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if not (self.accept_file_drops and has_file_payload(event.mimeData())):
            event.ignore()
            return
        try:
            paths = urls_from_mime(event.mimeData())
            logger.info("drop sobre la tabla: %d archivo(s) locales",
                        len(paths))
            if paths:
                self.pathsDropped.emit(paths)
            event.acceptProposedAction()
        except Exception as exc:  # noqa: BLE001
            logger.error("drop de la tabla fallo: %s", exc, exc_info=True)
            event.ignore()