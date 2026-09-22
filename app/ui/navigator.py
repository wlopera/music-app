"""Navegador de carpetas estilo Explorador de Windows (Fila superior, cuadrante izquierdo)."""

from pathlib import Path
from typing import Optional

import os

from PyQt6.QtCore import QByteArray, QMimeData, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QIcon
from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QStyle, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                             QWidget)

from app import fsutil
from app import logs

logger = logs.get_logger("navigator")

_OLE_FNAME_W = 'application/x-qt-windows-mime;value="FileNameW"'
_OLE_FNAME = 'application/x-qt-windows-mime;value="FileName"'


class _DragTree(QTreeWidget):
    """QTreeWidget cuyo arrastre inyecta rutas de archivo reales.

    Sin esto Qt arrastra el formato interno `application/x-qabstractitemmodeldatalist`
    (los indices del modelo), que el destino no puede convertir en archivos. Aqui se
    envian las mismas rutas que Windows Explorer: urls + text/uri-list + FileNameW."""
    def __init__(self, paths_provider, parent=None):
        super().__init__(parent)
        self._paths_provider = paths_provider

    def startDrag(self, actions) -> None:  # noqa: N802
        paths = self._paths_provider()
        if not paths:
            return
        logger.info("navegador: startDrag con %d archivo(s)", len(paths))
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


class FolderNavigator(QWidget):
    """Arbol de navegacion: subcarpetas y archivos permitidos del directorio actual.

    Con el filtro vacio muestra el directorio actual; al escribir texto busca de forma
    recursiva en toda la raiz seleccionada (los resultados aparecen con su ruta relativa).
    """

    copyRequested = pyqtSignal(list)      # Paths a copiar al staging
    openFile = pyqtSignal(Path)           # doble clic sobre un archivo
    fileClicked = pyqtSignal(Path)        # un clic sobre un archivo
    infoMessage = pyqtSignal(str)

    def __init__(self, extensions: list[str], parent=None):
        super().__init__(parent)
        self.extensions = list(extensions)
        self.current: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.up_btn = QToolButton()
        self.up_btn.setArrowType(Qt.ArrowType.LeftArrow)
        self.up_btn.setToolTip("Subir un nivel")
        self.up_btn.clicked.connect(self.go_up)
        self.root_btn = QToolButton()
        self.root_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.root_btn.setToolTip("Elegir raíz de búsqueda")
        self.root_btn.clicked.connect(self._pick_root)
        self.breadcrumb = QLabel("—")
        self.breadcrumb.setObjectName("secondaryLabel")
        toolbar.addWidget(self.up_btn)
        toolbar.addWidget(self.root_btn)
        toolbar.addWidget(self.breadcrumb, 1)
        layout.addLayout(toolbar)

        # Filtro (con debounce: la busqueda no bloquea la UI en cada tecla)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filtrar carpetas / archivos…")
        self.filter_edit.setObjectName("input")
        self._typing = QTimer(self)
        self._typing.setSingleShot(True)
        self._typing.setInterval(250)
        self._typing.timeout.connect(self.refresh)
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        # Copiar
        copy_row = QHBoxLayout()
        self.copy_btn = QPushButton("Copiar ▸")
        self.copy_btn.setObjectName("btnOutline")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_selected)
        copy_row.addStretch(1)
        copy_row.addWidget(self.copy_btn)
        layout.addLayout(copy_row)

        # Arbol
        self.tree = _DragTree(self._selected_paths)
        self.tree.setObjectName("treeFolders")
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setDragEnabled(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setAnimated(True)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemSelectionChanged.connect(self._update_copy_btn)
        layout.addWidget(self.tree, 1)

    # --- Estado ---------------------------------------------------------------
    def set_extensions(self, extensions: list[str]) -> None:
        self.extensions = list(extensions)
        self.refresh()

    def set_root(self, path: Optional[Path]) -> None:
        self.current = Path(path) if path else Path.home()
        logger.info("navegador raiz -> %s", self.current)
        self._typing.stop()
        self.refresh()

    def refresh(self) -> None:
        self.tree.clear()
        self.breadcrumb.setText(str(self.current or ""))
        if self.current is None or not self.current.is_dir():
            self._show_drives()
            return
        text = self.filter_edit.text().strip().lower()
        if text:
            self._search(self.current, text)
        else:
            self._populate(self.current)

    def _show_drives(self) -> None:
        self.breadcrumb.setText("Este equipo")
        for root in fsutil.list_drives():
            item = QTreeWidgetItem([root.name])
            item.setData(0, Qt.ItemDataRole.UserRole, root)
            item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon))
            item.setToolTip(0, str(root))
            self.tree.addTopLevelItem(item)
        logger.info("navegador: vista de unidades (%d)", self.tree.topLevelItemCount())

    def _populate(self, folder: Path) -> None:
        text = self.filter_edit.text().strip().lower()
        folders = fsutil.list_subfolders(folder)
        files = fsutil.list_allowed_files(folder, self.extensions)

        if text:
            folders = [f for f in folders if text in f.name.lower()]
            files = [f for f in files if text in f.name.lower()]

        dir_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        for d in folders:
            item = QTreeWidgetItem([d.name])
            item.setToolTip(0, str(d))
            self._theme_item(item, d)
            item.setIcon(0, dir_icon)
            self.tree.addTopLevelItem(item)
        for f in files:
            item = QTreeWidgetItem([f.name])
            item.setToolTip(0, str(f))
            self._theme_item(item, f)
            item.setIcon(0, file_icon)
            self.tree.addTopLevelItem(item)

        if not folders and not files:
            hint = QTreeWidgetItem(["Sin resultados"])
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            hint.setForeground(0, self.palette().placeholderText())
            self.tree.addTopLevelItem(hint)
        else:
            logger.info("navegador: %s -> %d carpeta(s), %d archivo(s)",
                        folder, len(folders), len(files))

    def _search(self, root: Path, text: str) -> None:
        """Busqueda recursiva de carpetas y archivos permitidos bajo `root`."""
        limit_entries = 4000     # archivos revisados
        limit_dirs = 2000        # carpetas visitadas (evita raices enormes)
        dir_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        matches: list[tuple[int, Path]] = []      # (0=folder, 1=file, path) ordenado
        scanned = 0
        dirs_visited = 0
        capped = False
        stack = [root]
        real_seen = {os.path.realpath(str(root))}
        while stack:
            if scanned >= limit_entries or dirs_visited >= limit_dirs:
                capped = True
                break
            d = stack.pop()
            dirs_visited += 1
            try:
                with os.scandir(d) as it:
                    entries = list(it)
            except OSError as exc:
                logger.warning("no se puede leer %s: %s", d, exc)
                continue
            for e in entries:
                try:
                    if e.is_dir(follow_symlinks=False):
                        # Evita bucles por junctions/enlaces simbolicos: cada carpeta
                        # real se visita una sola vez.
                        real = os.path.realpath(e.path)
                        if real in real_seen:
                            continue
                        real_seen.add(real)
                        if text in e.name.lower():
                            matches.append((0, Path(e.path)))
                        stack.append(Path(e.path))
                    elif e.is_file(follow_symlinks=False):
                        scanned += 1
                        if text in e.name.lower() and fsutil.is_allowed(e.path, self.extensions):
                            matches.append((1, Path(e.path)))
                except OSError:
                    continue

        rel = root
        matches.sort(key=lambda t: (t[1].name.lower(), str(t[1]).lower()))
        for kind, p in matches:
            try:
                disp = str(p.relative_to(rel)) if p != rel else p.name
            except ValueError:
                disp = str(p)
            item = QTreeWidgetItem([disp])
            item.setToolTip(0, str(p))
            self._theme_item(item, p)
            item.setIcon(0, dir_icon if kind == 0 else file_icon)
            self.tree.addTopLevelItem(item)

        if capped:
            hint = QTreeWidgetItem([f"…solo se mostraron los primeros {limit_entries} archivos revisados"])
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            hint.setForeground(0, self.palette().placeholderText())
            self.tree.addTopLevelItem(hint)
            logger.warning("busqueda '%s' en %s alcanzo el limite de %s entradas",
                           text, root, limit_entries)

        if not matches:
            hint = QTreeWidgetItem(["Sin resultados"])
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            hint.setForeground(0, self.palette().placeholderText())
            self.tree.addTopLevelItem(hint)

        logger.info("busqueda '%s' en %s -> %d resultado(s) (%d archivos, %d carpetas%s)",
                    text, root, len(matches), scanned, dirs_visited,
                    ", limite" if capped else "")
        self.infoMessage.emit(f"Búsqueda: {len(matches)} resultado(s)")

    def _theme_item(self, item: QTreeWidgetItem, path: Path) -> None:
        """Guarda el Path en el rol de datos como hacen el resto de listas."""
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        if path.is_file():
            item.setData(0, Qt.ItemDataRole.UserRole + 1, True)  # marca de archivo

    # --- Acciones ---------------------------------------------------------------
    def _apply_filter(self, _text: str) -> None:
        # Debounce: espera a dejar de escribir antes de recorrer el arbol.
        self._typing.start()

    def go_up(self) -> None:
        if self.current and self.current.parent:
            self.set_root(self.current.parent)

    def _pick_root(self) -> None:
        start = str(self.current) if self.current else ""
        chosen = QFileDialog.getExistingDirectory(self, "Elegir carpeta raíz de búsqueda", start)
        if chosen:
            logger.info("navegador: raiz elegida por el usuario -> %s", chosen)
            self._typing.stop()
            self.current = Path(chosen)
            self.refresh()

    def _selected_paths(self) -> list[Path]:
        paths = []
        for item in self.tree.selectedItems():
            p = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(p, Path) and p.is_file():
                paths.append(p)
        return paths

    def _update_copy_btn(self) -> None:
        self.copy_btn.setEnabled(bool(self._selected_paths()))

    def _copy_selected(self) -> None:
        paths = self._selected_paths()
        if paths:
            logger.info("navegador: copiar %d archivo(s) al staging", len(paths))
            self.copyRequested.emit(paths)

    # --- Eventos ---------------------------------------------------------------
    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(path, Path):
            return
        if path.is_dir():
            logger.info("navegador: entrar en %s", path)
            self._typing.stop()
            self.filter_edit.setText("")   # limpiar la busqueda al navegar
            self.set_root(path)
            return
        if path.is_file():
            logger.info("navegador: abrir media %s", path)
            self.openFile.emit(path)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(path, Path) and path.is_file():
            self.fileClicked.emit(path)


class FolderListView(QWidget):
    """Lista de subcarpetas de un directorio raiz (Fila inferior, cuadrante izquierdo).

    Un clic selecciona una carpeta para ver su contenido; doble clic navega dentro.
    """

    folderSelected = pyqtSignal(Path)
    setRootRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.up_btn = QToolButton()
        self.up_btn.setArrowType(Qt.ArrowType.LeftArrow)
        self.up_btn.setToolTip("Subir un nivel")
        self.up_btn.clicked.connect(self.go_up)
        self.root_btn = QToolButton()
        self.root_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.root_btn.setToolTip("Elegir carpeta base")
        self.root_btn.clicked.connect(self.setRootRequested.emit)
        self.breadcrumb = QLabel("—")
        self.breadcrumb.setObjectName("secondaryLabel")
        toolbar.addWidget(self.up_btn)
        toolbar.addWidget(self.root_btn)
        toolbar.addWidget(self.breadcrumb, 1)
        layout.addLayout(toolbar)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filtrar carpeta de canción…")
        self.filter_edit.setObjectName("input")
        self.filter_edit.textChanged.connect(self.refresh)
        layout.addWidget(self.filter_edit)

        self.tree = QTreeWidget()
        self.tree.setObjectName("treeFolders")
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setAnimated(True)
        self.tree.itemClicked.connect(self._on_clicked)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.tree, 1)

    def set_root(self, path: Path) -> None:
        self.current = Path(path)
        self.refresh()

    def refresh(self) -> None:
        self.tree.clear()
        self.breadcrumb.setText(str(self.current) if self.current else "—")
        if self.current is None or not self.current.is_dir():
            return
        text = self.filter_edit.text().strip().lower()
        dir_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        for d in fsutil.list_subfolders(self.current):
            if text and text not in d.name.lower():
                continue
            item = QTreeWidgetItem([d.name])
            item.setData(0, Qt.ItemDataRole.UserRole, d)
            item.setIcon(0, dir_icon)
            self.tree.addTopLevelItem(item)
        logger.info("biblioteca: %s -> %d carpeta(s)", self.current, self.tree.topLevelItemCount())

    def go_up(self) -> None:
        if self.current and self.current.parent:
            logger.info("biblioteca: subir a %s", self.current.parent)
            self.set_root(self.current.parent)

    def _path_at(self, item: QTreeWidgetItem) -> Optional[Path]:
        p = item.data(0, Qt.ItemDataRole.UserRole)
        return p if isinstance(p, Path) else None

    def _on_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        path = self._path_at(item)
        if path is not None:
            logger.info("biblioteca: seleccionar carpeta %s", path)
            self.folderSelected.emit(path)

    def _on_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        path = self._path_at(item)
        if path is not None:
            logger.info("biblioteca: entrar en %s", path)
            self.folderSelected.emit(path)
            self.set_root(path)

    def selected_path(self) -> Optional[Path]:
        items = self.tree.selectedItems()
        if items:
            return self._path_at(items[0])
        return None