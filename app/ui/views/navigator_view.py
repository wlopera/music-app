"""Vista «Navegador»: explorador de archivos multimedia estilo Windows Explorer.

Permite navegar por directorios con árbol jerárquico a la izquierda y tabla detallada
a la derecha, con soporte para:
  - Doble clic para reproducir audio y video con MediaModal.
  - Clic derecho con menú contextual completo (reproducir, renombrar, cortar, copiar, pegar,
    enviar a la papelera, abrir en explorador).
  - Eliminación segura enviando SIEMPRE a la Papelera de Reciclaje de Windows.
  - Drag & Drop fluido con compatibilidad nativa OLE / MIME de Windows.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (QByteArray, QDir, QMimeData, QModelIndex, QSortFilterProxyModel,
                          QTimer, QUrl, Qt, pyqtSignal)
from PyQt6.QtGui import QDrag, QFileSystemModel, QIcon
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QFrame,
                             QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QMenu, QMessageBox, QPushButton, QSizePolicy, QSplitter,
                             QStyle, QToolButton, QTreeView, QVBoxLayout, QWidget)

from app import fsutil
from app import logs
from app.config import ConfigManager

logger = logs.get_logger("navigator_view")

_OLE_FNAME_W = 'application/x-qt-windows-mime;value="FileNameW"'
_OLE_FNAME = 'application/x-qt-windows-mime;value="FileName"'

_AUDIO_VIDEO_EXTS = {
    ".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".aiff", ".wma",
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".m4v", ".mpg", ".mpeg",
}


class MediaFilterProxy(QSortFilterProxyModel):
    """Filtra la tabla para mostrar exclusivamente carpetas y archivos multimedia (audio/video),
    o todos los archivos según la configuración only_music."""

    def __init__(self, allowed_extensions, only_music: bool = True, parent=None):
        super().__init__(parent)
        self.allowed_extensions = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in allowed_extensions}
        self.only_music: bool = only_music
        self.search_text: str = ""
        self.current_dir: Optional[Path] = None

    def set_current_dir(self, directory: Path) -> None:
        self.current_dir = Path(directory).resolve()
        self.invalidateFilter()

    def set_only_music(self, enabled: bool) -> None:
        if self.only_music != enabled:
            self.only_music = enabled
            self.invalidateFilter()

    def set_allowed_extensions(self, exts) -> None:
        self.allowed_extensions = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in exts}
        self.invalidateFilter()

    def set_search_text(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.invalidateFilter()

    def _matches_pattern(self, file_name: str) -> bool:
        """Determina si el nombre coincide por subcadena o comodines estilo glob (*.mp3, demo*)."""
        if not self.search_text:
            return True
        name = file_name.lower()

        # Permitir múltiples patrones separados por coma o punto y coma (ej. "*.mp3, *.wav")
        tokens = [t.strip() for t in self.search_text.replace(";", ",").split(",") if t.strip()]
        if not tokens:
            tokens = [self.search_text]

        for token in tokens:
            if "*" in token or "?" in token:
                if fnmatch.fnmatch(name, token):
                    return True
            else:
                if token in name:
                    return True
        return False

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        src_model = self.sourceModel()
        if not isinstance(src_model, QFileSystemModel):
            return True
        idx = src_model.index(source_row, 0, source_parent)
        info = src_model.fileInfo(idx)
        item_path = Path(info.filePath()).resolve()

        # 1. Regla crítica: los ancestros del directorio actual y el propio directorio actual
        #    NUNCA deben filtrarse; de lo contrario Qt invalida la rama raíz del proxy.
        if self.current_dir:
            try:
                if self.current_dir.is_relative_to(item_path):
                    return True
            except Exception:
                pass

        # 2. Si es una carpeta hija dentro de current_dir:
        if info.isDir():
            if self.search_text:
                return self._matches_pattern(info.fileName())
            return True

        # 3. Si es un archivo:
        if self.only_music:
            ext = "." + info.suffix().lower()
            if ext not in self.allowed_extensions:
                return False

        if self.search_text:
            return self._matches_pattern(info.fileName())

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        """Ordenamiento preciso estilo Windows Explorer: carpetas arriba, tamaño numérico y fechas reales."""
        src = self.sourceModel()
        if not isinstance(src, QFileSystemModel):
            return super().lessThan(left, right)

        info_left = src.fileInfo(left)
        info_right = src.fileInfo(right)
        col = left.column()

        # Carpetas siempre agrupadas arriba (tanto en orden ascendente como descendente)
        is_dir_left = info_left.isDir()
        is_dir_right = info_right.isDir()
        if is_dir_left != is_dir_right:
            if self.sortOrder() == Qt.SortOrder.AscendingOrder:
                return is_dir_left
            else:
                return not is_dir_left

        if col == 1:  # Tamaño numérico (bytes)
            if not is_dir_left and not is_dir_right:
                sz_l = info_left.size()
                sz_r = info_right.size()
                if sz_l != sz_r:
                    return sz_l < sz_r
        elif col == 2:  # Tipo (extensión)
            type_l = (info_left.suffix() or info_left.fileName()).lower()
            type_r = (info_right.suffix() or info_right.fileName()).lower()
            if type_l != type_r:
                return type_l < type_r
        elif col == 3:  # Fecha de creación (cronológico real en milisegundos)
            dt_l = info_left.birthTime()
            dt_r = info_right.birthTime()
            t_l = dt_l.toMSecsSinceEpoch() if dt_l.isValid() and dt_l.toSecsSinceEpoch() > 0 else 0
            t_r = dt_r.toMSecsSinceEpoch() if dt_r.isValid() and dt_r.toSecsSinceEpoch() > 0 else 0
            if t_l == 0 or t_r == 0:
                try:
                    if t_l == 0:
                        t_l = int(os.stat(info_left.filePath()).st_ctime * 1000)
                    if t_r == 0:
                        t_r = int(os.stat(info_right.filePath()).st_ctime * 1000)
                except Exception:
                    pass
            if t_l != t_r:
                return t_l < t_r

        # Columna 0 (Nombre) o empate: alfabético insensible a mayúsculas
        return info_left.fileName().lower() < info_right.fileName().lower()


class _CustomFileSystemModel(QFileSystemModel):
    """Modelo de sistema de archivos con encabezados y formatos estándar en español."""

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            headers = ["Nombre", "Tamaño", "Tipo", "Fecha de creación"]
            if 0 <= section < len(headers):
                return headers[section]
        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 1:
                # Tamaño: carpetas vacías, archivos formateados en KB / MB (sin KiB / MiB)
                info = self.fileInfo(index)
                if info.isDir():
                    return ""
                return fsutil.human_size(info.size())
            elif col == 3:
                # Fecha de creación con formato dd/mm/yyyy HH:mm
                info = self.fileInfo(index)
                dt = info.birthTime()
                if dt.isValid() and dt.toSecsSinceEpoch() > 0:
                    return dt.toString("dd/MM/yyyy HH:mm")
                try:
                    st = os.stat(info.filePath())
                    return fsutil.format_timestamp(st.st_ctime)
                except Exception:
                    return "—"
        elif role == Qt.ItemDataRole.TextAlignmentRole and col == 1:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return super().data(index, role)


class _DraggableDetailView(QTreeView):
    """Vista detallada derecha con soporte de Drag & Drop y atajos de Windows."""

    renameRequested = pyqtSignal(Path)
    deleteRequested = pyqtSignal(list)
    playRequested = pyqtSignal(Path)
    enterFolderRequested = pyqtSignal(Path)
    copyRequested = pyqtSignal(list)
    cutRequested = pyqtSignal(list)
    pasteRequested = pyqtSignal()
    dropFilesReceived = pyqtSignal(list, Path)  # (sources, target_folder)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setAnimated(True)
        self.setRootIsDecorated(False)
        self.setSortingEnabled(True)

    def startDrag(self, supported_actions: Qt.DropAction) -> None:  # noqa: N802
        paths = self.selected_paths()
        if not paths:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
        uri_list = "".join(f"file:///{str(p).replace(chr(92), '/')}\r\n" for p in paths)
        mime.setData("text/uri-list", QByteArray(uri_list.encode("utf-8")))
        joined = "\x00".join(str(p) for p in paths) + "\x00"
        mime.setData(_OLE_FNAME_W, QByteArray(joined.encode("utf-16-le")))
        mime.setData(_OLE_FNAME, QByteArray(joined.encode("cp1252", "replace")))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasFormat(_OLE_FNAME_W) or event.mimeData().hasFormat("text/uri-list"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasFormat(_OLE_FNAME_W) or event.mimeData().hasFormat("text/uri-list"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        paths = [Path(u.toLocalFile()) for u in urls if u.isLocalFile()]
        if not paths:
            super().dropEvent(event)
            return

        # Detectar si se soltó sobre una subcarpeta específica de la tabla
        idx = self.indexAt(event.position().toPoint())
        target_dir = None
        if idx.isValid():
            p = self.path_from_index(idx)
            if p and p.is_dir():
                target_dir = p

        parent_view = self.parent()
        if target_dir is None and hasattr(parent_view, 'current_dir'):
            target_dir = parent_view.current_dir

        if target_dir:
            self.dropFilesReceived.emit(paths, target_dir)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_F2:
            paths = self.selected_paths()
            if paths:
                self.renameRequested.emit(paths[0])
            return
        elif key == Qt.Key.Key_Delete:
            paths = self.selected_paths()
            if paths:
                self.deleteRequested.emit(paths)
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            paths = self.selected_paths()
            if paths:
                p = paths[0]
                if p.is_dir():
                    self.enterFolderRequested.emit(p)
                else:
                    self.playRequested.emit(p)
            return
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_C:
            self.copyRequested.emit(self.selected_paths())
            return
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_X:
            self.cutRequested.emit(self.selected_paths())
            return
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_V:
            self.pasteRequested.emit()
            return
        super().keyPressEvent(event)

    def path_from_index(self, index: QModelIndex) -> Optional[Path]:
        if not index.isValid():
            return None
        model = self.model()
        if isinstance(model, QSortFilterProxyModel):
            src_idx = model.mapToSource(index)
            src_model = model.sourceModel()
            if isinstance(src_model, QFileSystemModel):
                return Path(src_model.filePath(src_idx))
        elif isinstance(model, QFileSystemModel):
            return Path(model.filePath(index))
        return None

    def selected_paths(self) -> list[Path]:
        selection_model = self.selectionModel()
        if not selection_model:
            return []
        rows = selection_model.selectedRows(0)
        paths = []
        for r in rows:
            p = self.path_from_index(r)
            if p:
                paths.append(p)
        return paths


class NavigatorView(QWidget):
    """Vista completa del Navegador de Archivos Multimedia (estilo Windows Explorer)."""

    statusMessage = pyqtSignal(str, int)

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self._media_preview = None
        self._clipboard_paths: list[Path] = []
        self._clipboard_action: str = ""  # 'copy' o 'cut'

        # Historial de navegación (Atrás / Adelante)
        self._history: list[Path] = []
        self._history_idx: int = -1

        # Carpeta actual de trabajo (por defecto carpeta_base o raíz de navegación)
        initial_dir = Path(config.carpeta_base) if config.carpeta_base else Path.home()
        if not initial_dir.exists():
            initial_dir = Path.home()
        self.current_dir: Path = initial_dir

        self._build_ui()
        self.navigate_to(self.current_dir, add_history=True)

    # --- Construcción UI -------------------------------------------------------------
    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(14, 14, 14, 14)
        root_lay.setSpacing(10)

        # 1. Barra superior: botones de acción e historial
        self._build_toolbar(root_lay)

        # 2. Barra de ruta / dirección (Breadcrumb) + filtro rápido
        self._build_path_bar(root_lay)

        # 3. Contenedor principal con QSplitter horizontal (Árbol a la izquierda, Tabla a la derecha)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("navSplitter")
        self.splitter.setChildrenCollapsible(False)

        self._build_tree_panel()
        self._build_detail_panel()

        self.splitter.addWidget(self.tree_card)
        self.splitter.addWidget(self.detail_card)
        self.splitter.setSizes([280, 720])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        root_lay.addWidget(self.splitter, 1)

        # 4. Barra de estado inferior
        self.bottom_status = QLabel("Listo")
        self.bottom_status.setObjectName("mutedLabel")
        root_lay.addWidget(self.bottom_status)

    def _build_toolbar(self, parent_layout: QVBoxLayout) -> None:
        bar = QWidget()
        bar.setObjectName("controlBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(6)

        # Navegación Atrás / Adelante / Arriba
        self.btn_back = QToolButton()
        self.btn_back.setText("◀")
        self.btn_back.setObjectName("btnIconHeader")
        self.btn_back.setToolTip("Atrás (Alt+Izquierda)")
        self.btn_back.clicked.connect(self._go_back)

        self.btn_forward = QToolButton()
        self.btn_forward.setText("▶")
        self.btn_forward.setObjectName("btnIconHeader")
        self.btn_forward.setToolTip("Adelante (Alt+Derecha)")
        self.btn_forward.clicked.connect(self._go_forward)

        self.btn_up = QToolButton()
        self.btn_up.setText("▲")
        self.btn_up.setObjectName("btnIconHeader")
        self.btn_up.setToolTip("Subir un nivel (Alt+Arriba)")
        self.btn_up.clicked.connect(self._go_up)

        self.btn_root = QToolButton()
        self.btn_root.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.btn_root.setObjectName("btnIconHeader")
        self.btn_root.setToolTip("Elegir carpeta para explorar")
        self.btn_root.clicked.connect(self._choose_folder)

        lay.addWidget(self.btn_back)
        lay.addWidget(self.btn_forward)
        lay.addWidget(self.btn_up)
        lay.addWidget(self.btn_root)

        # Separador visual
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #374151; margin: 2px 4px;")
        lay.addWidget(sep1)

        # Botón Nueva Carpeta
        self.btn_new_folder = QPushButton("📁+ Nueva Carpeta")
        self.btn_new_folder.setObjectName("btnOutline")
        self.btn_new_folder.setToolTip("Crear una nueva subcarpeta en el directorio actual")
        self.btn_new_folder.clicked.connect(self._create_folder)
        lay.addWidget(self.btn_new_folder)

        # Botón Renombrar
        self.btn_rename = QPushButton("✏️ Renombrar")
        self.btn_rename.setObjectName("btnOutline")
        self.btn_rename.setToolTip("Renombrar el elemento seleccionado (F2)")
        self.btn_rename.clicked.connect(self._on_rename_clicked)
        lay.addWidget(self.btn_rename)

        # Portapapeles: Cortar, Copiar, Pegar
        self.btn_cut = QToolButton()
        self.btn_cut.setText("✂️")
        self.btn_cut.setObjectName("btnIconHeader")
        self.btn_cut.setToolTip("Cortar (Ctrl+X)")
        self.btn_cut.clicked.connect(self._on_cut_clicked)

        self.btn_copy = QToolButton()
        self.btn_copy.setText("📋")
        self.btn_copy.setObjectName("btnIconHeader")
        self.btn_copy.setToolTip("Copiar (Ctrl+C)")
        self.btn_copy.clicked.connect(self._on_copy_clicked)

        self.btn_paste = QToolButton()
        self.btn_paste.setText("📥")
        self.btn_paste.setObjectName("btnIconHeader")
        self.btn_paste.setToolTip("Pegar (Ctrl+V)")
        self.btn_paste.clicked.connect(self._on_paste_clicked)

        lay.addWidget(self.btn_cut)
        lay.addWidget(self.btn_copy)
        lay.addWidget(self.btn_paste)

        # Separador
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #374151; margin: 2px 4px;")
        lay.addWidget(sep2)

        # Botón Papelera de Reciclaje (con destacado en tono suave)
        self.btn_trash = QPushButton("🗑️ Enviar a Papelera")
        self.btn_trash.setObjectName("btnDanger")
        self.btn_trash.setToolTip("Enviar elementos seleccionados a la Papelera de reciclaje de Windows (recuperables)")
        self.btn_trash.clicked.connect(self._on_trash_clicked)
        lay.addWidget(self.btn_trash)

        # Botón Conmutador: Solo Multimedia / Todos los Archivos
        self.btn_filter_music = QPushButton("🎵 Solo Multimedia" if self.config.only_music else "📄 Todos los Archivos")
        self.btn_filter_music.setObjectName("btnViewMode")
        self.btn_filter_music.setCheckable(True)
        self.btn_filter_music.setChecked(self.config.only_music)
        self.btn_filter_music.setToolTip("Alternar entre ver solo archivos de audio/video o ver todos los archivos (config.json: only_music)")
        self.btn_filter_music.clicked.connect(self._toggle_filter_music)
        lay.addWidget(self.btn_filter_music)

        lay.addStretch(1)
        parent_layout.addWidget(bar)

    def _build_path_bar(self, parent_layout: QVBoxLayout) -> None:
        path_box = QWidget()
        lay = QHBoxLayout(path_box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lbl = QLabel("RUTA:")
        lbl.setObjectName("controlLabel")
        lay.addWidget(lbl)

        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("input")
        self.path_edit.setPlaceholderText("Ruta del directorio…")
        self.path_edit.returnPressed.connect(self._on_path_entered)
        lay.addWidget(self.path_edit, 1)

        # Campo de filtro en tiempo real con soporte de texto y comodines (* y ?)
        self.filter_edit = QLineEdit()
        self.filter_edit.setObjectName("input")
        self.filter_edit.setPlaceholderText("🔍 Filtrar (*.mp3, demo*)…")
        self.filter_edit.setToolTip("Filtrar por texto o comodines glob (* y ?).\nEjemplos: *.mp3, demo*, *.mp3, *.wav")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setFixedWidth(240)
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        lay.addWidget(self.filter_edit)

        parent_layout.addWidget(path_box)

    def _build_tree_panel(self) -> None:
        self.tree_card = QFrame()
        self.tree_card.setObjectName("card")
        lay = QVBoxLayout(self.tree_card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        header = QLabel("CARPETAS")
        header.setObjectName("sectionHeaderTitle")
        header.setStyleSheet("font-size: 8.5pt; font-weight: 700; color: #60A5FA; letter-spacing: 1px;")
        lay.addWidget(header)

        # Modelo del árbol: solo directorios
        self.tree_model = _CustomFileSystemModel()
        self.tree_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Drives)
        self.tree_model.setRootPath("")

        self.tree_view = QTreeView()
        self.tree_view.setObjectName("treeFolders")
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setHeaderHidden(True)
        # Ocultar columnas 1, 2, 3 en el árbol para que solo muestre el nombre
        for col in (1, 2, 3):
            self.tree_view.hideColumn(col)
        self.tree_view.setAnimated(True)
        self.tree_view.clicked.connect(self._on_tree_item_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._on_tree_context_menu)

        lay.addWidget(self.tree_view, 1)

    def _build_detail_panel(self) -> None:
        self.detail_card = QFrame()
        self.detail_card.setObjectName("card")
        lay = QVBoxLayout(self.detail_card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.detail_header_lbl = QLabel("ARCHIVOS MULTIMEDIA" if self.config.only_music else "TODOS LOS ARCHIVOS")
        self.detail_header_lbl.setObjectName("sectionHeaderTitle")
        self.detail_header_lbl.setStyleSheet("font-size: 8.5pt; font-weight: 700; color: #60A5FA; letter-spacing: 1px;")
        lay.addWidget(self.detail_header_lbl)

        # Modelo de la tabla de archivos
        self.detail_model = _CustomFileSystemModel()
        self.detail_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.detail_model.setRootPath("")

        # Proxy para filtrado multimedia y búsqueda por texto
        self.proxy_model = MediaFilterProxy(
            self.config.extensiones_permitidas,
            only_music=self.config.only_music,
            parent=self
        )
        self.proxy_model.setSourceModel(self.detail_model)

        self.detail_view = _DraggableDetailView(self)
        self.detail_view.setObjectName("fileTable")
        self.detail_view.setModel(self.proxy_model)

        # Ajustes de cabecera y anchos
        hdr = self.detail_view.header()
        hdr.setStretchLastSection(True)
        hdr.setSortIndicatorShown(True)
        hdr.setSectionsClickable(True)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.detail_view.setSortingEnabled(True)
        self.detail_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        # Conectar eventos de la vista
        self.detail_view.doubleClicked.connect(self._on_detail_double_clicked)
        self.detail_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.detail_view.customContextMenuRequested.connect(self._on_detail_context_menu)

        self.detail_view.renameRequested.connect(self._rename_path)
        self.detail_view.deleteRequested.connect(self._trash_paths)
        self.detail_view.playRequested.connect(self._open_media)
        self.detail_view.enterFolderRequested.connect(lambda p: self.navigate_to(p, add_history=True))
        self.detail_view.copyRequested.connect(self._set_clipboard_copy)
        self.detail_view.cutRequested.connect(self._set_clipboard_cut)
        self.detail_view.pasteRequested.connect(self._on_paste_clicked)
        self.detail_view.dropFilesReceived.connect(self._handle_dropped_files)

        lay.addWidget(self.detail_view, 1)

    # --- Navegación y Sincronización -------------------------------------------------
    def navigate_to(self, folder: Path, add_history: bool = True) -> None:
        p = Path(folder).resolve()
        if not p.is_dir():
            logger.warning("navegador: la ruta no es un directorio valido %s", p)
            return

        self.current_dir = p
        self.proxy_model.set_current_dir(p)
        self.path_edit.setText(str(p))

        # 1. Posicionar árbol izquierdo
        tree_idx = self.tree_model.index(str(p))
        if tree_idx.isValid():
            self.tree_view.setCurrentIndex(tree_idx)
            self.tree_view.scrollTo(tree_idx)

        # 2. Posicionar tabla derecha
        src_idx = self.detail_model.index(str(p))
        proxy_idx = self.proxy_model.mapFromSource(src_idx)
        self.detail_view.setRootIndex(proxy_idx)

        # 3. Historial
        if add_history:
            if self._history_idx < len(self._history) - 1:
                self._history = self._history[:self._history_idx + 1]
            self._history.append(p)
            self._history_idx = len(self._history) - 1

        self._update_history_buttons()
        self._update_status_summary()

    def _update_history_buttons(self) -> None:
        self.btn_back.setEnabled(self._history_idx > 0)
        self.btn_forward.setEnabled(self._history_idx < len(self._history) - 1)
        self.btn_up.setEnabled(bool(self.current_dir.parent and self.current_dir.parent != self.current_dir))

    def _go_back(self) -> None:
        if self._history_idx > 0:
            self._history_idx -= 1
            self.navigate_to(self._history[self._history_idx], add_history=False)

    def _go_forward(self) -> None:
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self.navigate_to(self._history[self._history_idx], add_history=False)

    def _go_up(self) -> None:
        parent = self.current_dir.parent
        if parent and parent != self.current_dir and parent.exists():
            self.navigate_to(parent, add_history=True)

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta para explorar",
            str(self.current_dir)
        )
        if chosen:
            self.navigate_to(Path(chosen), add_history=True)

    def _on_path_entered(self) -> None:
        txt = self.path_edit.text().strip()
        p = Path(txt)
        if p.is_dir():
            self.navigate_to(p, add_history=True)
        else:
            QMessageBox.warning(self, "Ruta no válida", f"El directorio no existe:\n{txt}")
            self.path_edit.setText(str(self.current_dir))

    def _on_filter_changed(self, text: str) -> None:
        self.proxy_model.set_search_text(text)
        self._update_status_summary()

    def _toggle_filter_music(self) -> None:
        new_val = self.btn_filter_music.isChecked()
        self.config.only_music = new_val
        self.proxy_model.set_only_music(new_val)
        self.btn_filter_music.setText("🎵 Solo Multimedia" if new_val else "📄 Todos los Archivos")
        if hasattr(self, 'detail_header_lbl'):
            self.detail_header_lbl.setText("ARCHIVOS MULTIMEDIA" if new_val else "TODOS LOS ARCHIVOS")
        msg = "Filtro activado: mostrando solo archivos de audio y video." if new_val else "Filtro desactivado: mostrando todos los tipos de archivos."
        self.statusMessage.emit(msg, 2500)
        self._update_status_summary()

    def apply_config(self) -> None:
        """Aplica cambios en extensiones_permitidas u only_music de la configuración."""
        self.proxy_model.set_allowed_extensions(self.config.extensiones_permitidas)
        self.proxy_model.set_only_music(self.config.only_music)
        self.btn_filter_music.setChecked(self.config.only_music)
        self.btn_filter_music.setText("🎵 Solo Multimedia" if self.config.only_music else "📄 Todos los Archivos")
        if hasattr(self, 'detail_header_lbl'):
            self.detail_header_lbl.setText("ARCHIVOS MULTIMEDIA" if self.config.only_music else "TODOS LOS ARCHIVOS")
        self._update_status_summary()

    def _on_tree_item_clicked(self, index: QModelIndex) -> None:
        path_str = self.tree_model.filePath(index)
        if path_str:
            p = Path(path_str)
            if p.is_dir():
                self.navigate_to(p, add_history=True)

    def _on_detail_double_clicked(self, proxy_idx: QModelIndex) -> None:
        src_idx = self.proxy_model.mapToSource(proxy_idx)
        path_str = self.detail_model.filePath(src_idx)
        if not path_str:
            return
        p = Path(path_str)
        if p.is_dir():
            self.navigate_to(p, add_history=True)
        else:
            self._open_media(p)

    def _update_status_summary(self) -> None:
        try:
            src_idx = self.detail_model.index(str(self.current_dir))
            proxy_idx = self.proxy_model.mapFromSource(src_idx)
            visible_rows = self.proxy_model.rowCount(proxy_idx)

            if self.proxy_model.search_text:
                self.bottom_status.setText(
                    f"🔍 {visible_rows} elemento(s) coincidente(s) con «{self.proxy_model.search_text}» | Ruta: {self.current_dir}"
                )
            else:
                items = list(self.current_dir.iterdir())
                dirs = sum(1 for i in items if i.is_dir())
                allowed = self.proxy_model.allowed_extensions
                if self.proxy_model.only_music:
                    media_files = sum(1 for i in items if i.is_file() and i.suffix.lower() in allowed)
                    lbl = f"📁 {dirs} carpeta(s) · 🎵 {media_files} archivo(s) multimedia"
                else:
                    total_files = sum(1 for i in items if i.is_file())
                    lbl = f"📁 {dirs} carpeta(s) · 📄 {total_files} archivo(s) en total"
                self.bottom_status.setText(f"{lbl} | Ruta: {self.current_dir}")
        except Exception:
            self.bottom_status.setText(f"Ruta: {self.current_dir}")

    def _refresh_all(self) -> None:
        self.tree_model.setRootPath("")
        self.detail_model.setRootPath("")
        self.navigate_to(self.current_dir, add_history=False)
        self.statusMessage.emit("Vista actualizada.", 2000)

    # --- Acciones CRUD y Papelera de Reciclaje ---------------------------------------
    def _create_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "Nueva Carpeta", "Introduce el nombre de la carpeta:")
        if not ok or not name.strip():
            return
        name = name.strip()
        # Validar caracteres ilegales en Windows
        illegal = '<>:"/\\|?*'
        if any(c in name for c in illegal):
            QMessageBox.warning(self, "Nombre no válido", f"El nombre no puede contener ninguno de los siguientes caracteres:\n{illegal}")
            return

        new_dir = self.current_dir / name
        if new_dir.exists():
            QMessageBox.warning(self, "Carpeta existente", f"Ya existe un elemento con el nombre «{name}».")
            return

        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            self.statusMessage.emit(f"Carpeta «{name}» creada con éxito.", 3000)
            self._refresh_all()
        except Exception as exc:
            logger.error("error creando carpeta %s: %s", new_dir, exc)
            QMessageBox.critical(self, "Error al crear carpeta", f"No se pudo crear la carpeta:\n{exc}")

    def _on_rename_clicked(self) -> None:
        paths = self.detail_view.selected_paths()
        if not paths:
            QMessageBox.information(self, "Sin selección", "Selecciona un archivo o carpeta para renombrar.")
            return
        self._rename_path(paths[0])

    def _rename_path(self, path: Path) -> None:
        from app.ui.rename_dialog import prompt_rename
        new_path = prompt_rename(path, parent=self)
        if new_path is not None:
            self.statusMessage.emit(f"Renombrado a «{new_path.name}».", 3500)
            self._refresh_all()

    def _on_trash_clicked(self) -> None:
        paths = self.detail_view.selected_paths()
        if not paths:
            QMessageBox.information(self, "Sin selección", "Selecciona uno o más elementos para enviar a la papelera.")
            return
        self._trash_paths(paths)

    def _trash_paths(self, paths: list[Path]) -> None:
        if not paths:
            return

        # Si el elemento en reproducción coincide con alguno de los que se borran, cerrarlo
        if self._media_preview and hasattr(self._media_preview, 'file_path'):
            if any(p.resolve() == self._media_preview.file_path.resolve() for p in paths):
                self._media_preview.close()
                self._media_preview = None

        if len(paths) == 1:
            item_name = paths[0].name
            msg = (f"¿Deseas enviar «{item_name}» a la Papelera de reciclaje de Windows?\n\n"
                   f"Podrás recuperarlo en cualquier momento desde Windows.")
        else:
            msg = (f"¿Deseas enviar los {len(paths)} elementos seleccionados a la Papelera de reciclaje de Windows?\n\n"
                   f"Podrás recuperarlos en cualquier momento desde Windows.")

        res = QMessageBox.question(
            self, "Confirmar envío a la papelera", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        recycled_count = 0
        errors = []
        for p in paths:
            ok = fsutil.send_to_recycle_bin(p)
            if ok:
                recycled_count += 1
            else:
                errors.append(p.name)

        if errors:
            QMessageBox.warning(
                self, "Aviso de eliminación",
                f"No se pudieron enviar a la papelera:\n" + "\n".join(errors)
            )

        if recycled_count > 0:
            self.statusMessage.emit(f"{recycled_count} elemento(s) enviado(s) a la Papelera de reciclaje.", 3500)
            self._refresh_all()

    # --- Portapapeles (Cortar, Copiar, Pegar) ----------------------------------------
    def _on_cut_clicked(self) -> None:
        paths = self.detail_view.selected_paths()
        if paths:
            self._set_clipboard_cut(paths)

    def _on_copy_clicked(self) -> None:
        paths = self.detail_view.selected_paths()
        if paths:
            self._set_clipboard_copy(paths)

    def _set_clipboard_copy(self, paths: list[Path]) -> None:
        self._clipboard_paths = list(paths)
        self._clipboard_action = "copy"
        self.statusMessage.emit(f"{len(paths)} elemento(s) copiado(s) al portapapeles.", 2500)

    def _set_clipboard_cut(self, paths: list[Path]) -> None:
        self._clipboard_paths = list(paths)
        self._clipboard_action = "cut"
        self.statusMessage.emit(f"{len(paths)} elemento(s) cortado(s) al portapapeles.", 2500)

    def _on_paste_clicked(self) -> None:
        if not self._clipboard_paths:
            self.statusMessage.emit("El portapapeles interno está vacío.", 2500)
            return

        target_dir = self.current_dir
        count = 0
        for src in self._clipboard_paths:
            if not src.exists():
                continue
            dest = target_dir / src.name
            try:
                if self._clipboard_action == "cut":
                    if src.resolve() != dest.resolve():
                        shutil.move(src, dest)
                        count += 1
                else:  # copy
                    if src.is_dir():
                        if src.resolve() != dest.resolve():
                            shutil.copytree(src, dest, dirs_exist_ok=True)
                            count += 1
                    else:
                        if src.resolve() != dest.resolve():
                            shutil.copy2(src, dest)
                            count += 1
            except Exception as exc:
                logger.error("error pegando %s en %s: %s", src, dest, exc)

        action_name = "movido(s)" if self._clipboard_action == "cut" else "copiado(s)"
        self.statusMessage.emit(f"{count} elemento(s) {action_name} a «{target_dir.name}».", 3000)

        if self._clipboard_action == "cut":
            self._clipboard_paths.clear()
            self._clipboard_action = ""

        self._refresh_all()

    def _handle_dropped_files(self, sources: list[Path], target_dir: Path) -> None:
        moved = 0
        for src in sources:
            if not src.exists():
                continue
            dest = target_dir / src.name
            if src.resolve() == dest.resolve():
                continue
            try:
                shutil.move(src, dest)
                moved += 1
            except Exception as exc:
                logger.error("error en drag-drop moviendo %s a %s: %s", src, dest, exc)

        if moved > 0:
            self.statusMessage.emit(f"{moved} archivo(s) movido(s) a «{target_dir.name}».", 3000)
            self._refresh_all()

    # --- Menús Contextuales (Clic Derecho) -------------------------------------------
    def _on_detail_context_menu(self, pos) -> None:
        menu = QMenu(self)
        selected_paths = self.detail_view.selected_paths()

        if selected_paths:
            primary = selected_paths[0]
            ext = primary.suffix.lower()
            if ext in _AUDIO_VIDEO_EXTS or ext in self.proxy_model.allowed_extensions:
                act_play = menu.addAction("▶  Reproducir / Visualizar")
                act_play.triggered.connect(lambda: self._open_media(primary))
                menu.addSeparator()

            act_rename = menu.addAction("✏️  Renombrar… (F2)")
            act_rename.triggered.connect(lambda: self._rename_path(primary))

            act_cut = menu.addAction("✂️  Cortar (Ctrl+X)")
            act_cut.triggered.connect(lambda: self._set_clipboard_cut(selected_paths))

            act_copy = menu.addAction("📋  Copiar (Ctrl+C)")
            act_copy.triggered.connect(lambda: self._set_clipboard_copy(selected_paths))

        if self._clipboard_paths:
            act_paste = menu.addAction(f"📥  Pegar en «{self.current_dir.name}» (Ctrl+V)")
            act_paste.triggered.connect(self._on_paste_clicked)

        menu.addSeparator()

        act_new = menu.addAction("📁+ Nueva Carpeta…")
        act_new.triggered.connect(self._create_folder)

        if selected_paths:
            act_trash = menu.addAction("🗑️  Enviar a la Papelera de reciclaje (Supr)")
            act_trash.triggered.connect(lambda: self._trash_paths(selected_paths))

            act_explorer = menu.addAction("📂  Abrir en Explorador de Windows")
            act_explorer.triggered.connect(lambda: self._open_in_windows_explorer(selected_paths[0]))
        else:
            act_explorer = menu.addAction("📂  Abrir esta carpeta en Explorador de Windows")
            act_explorer.triggered.connect(lambda: self._open_in_windows_explorer(self.current_dir))

        menu.addSeparator()
        act_refresh = menu.addAction("🔄  Actualizar")
        act_refresh.triggered.connect(self._refresh_all)

        menu.exec(self.detail_view.viewport().mapToGlobal(pos))

    def _on_tree_context_menu(self, pos) -> None:
        idx = self.tree_view.indexAt(pos)
        if not idx.isValid():
            return
        path_str = self.tree_model.filePath(idx)
        if not path_str:
            return
        p = Path(path_str)

        menu = QMenu(self)
        act_open = menu.addAction("📂  Abrir carpeta")
        act_open.triggered.connect(lambda: self.navigate_to(p, add_history=True))

        act_new = menu.addAction("📁+ Nueva Subcarpeta…")
        act_new.triggered.connect(lambda: self._create_subfolder(p))

        act_rename = menu.addAction("✏️  Renombrar…")
        act_rename.triggered.connect(lambda: self._rename_path(p))

        menu.addSeparator()
        act_trash = menu.addAction("🗑️  Enviar a la Papelera de reciclaje")
        act_trash.triggered.connect(lambda: self._trash_paths([p]))

        act_explorer = menu.addAction("📂  Abrir en Explorador de Windows")
        act_explorer.triggered.connect(lambda: self._open_in_windows_explorer(p))

        menu.exec(self.tree_view.viewport().mapToGlobal(pos))

    def _create_subfolder(self, parent_folder: Path) -> None:
        name, ok = QInputDialog.getText(self, "Nueva Carpeta", f"Crear subcarpeta en «{parent_folder.name}»:")
        if not ok or not name.strip():
            return
        name = name.strip()
        illegal = '<>:"/\\|?*'
        if any(c in name for c in illegal):
            QMessageBox.warning(self, "Nombre no válido", f"El nombre no puede contener: {illegal}")
            return
        new_d = parent_folder / name
        try:
            new_d.mkdir(parents=True, exist_ok=True)
            self._refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo crear la carpeta:\n{exc}")

    def _open_in_windows_explorer(self, target: Path) -> None:
        try:
            target_str = str(target.resolve())
            if target.is_dir():
                subprocess.Popen(["explorer.exe", target_str])
            else:
                subprocess.Popen(["explorer.exe", f"/select,{target_str}"])
        except Exception as exc:
            logger.error("error abriendo explorer %s: %s", target, exc)

    # --- Previsualización Multimedia ------------------------------------------------
    def _open_media(self, path: Path) -> None:
        ext = path.suffix.lower()
        if ext not in _AUDIO_VIDEO_EXTS and ext not in self.proxy_model.allowed_extensions:
            return

        from app.ui.media_modal import MediaModal
        t0 = time.monotonic()
        logger.info("navegador abrir media: %s", path)
        try:
            modal = MediaModal(path, self)
            modal.setWindowModality(Qt.WindowModality.ApplicationModal)
            modal.show()
            self._media_preview = modal
            logger.info("navegador preview abierta (%s) en %.1fms", path.name,
                        (time.monotonic() - t0) * 1000)
        except Exception as exc:
            logger.error("error reproduciendo %s: %s", path, exc, exc_info=True)
            QMessageBox.critical(self, "Error de reproducción", f"No se pudo abrir «{path.name}»:\n{exc}")
