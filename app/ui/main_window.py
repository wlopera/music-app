"""Ventana principal: regiones colapsables, navegador, staging, biblioteca y control."""

from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QSplitter, QStatusBar,
                             QToolButton, QVBoxLayout, QWidget, QSizePolicy, QPushButton)

from app import fsutil
from app import logs
from app.config import ConfigManager
from app.sidecar import Sidecar
from app.ui.navigator import FolderListView, FolderNavigator
from app.ui.panels import SectionPanel
from app.ui.staging import StagingPanel
from app.ui.settings_dialog import SettingsDialog

logger = logs.get_logger("main_window")


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.setWindowTitle("Music-App")
        
        # Dimensiones compactas optimizadas
        self.resize(1120, 720)
        self.setMinimumSize(820, 520)

        central = QWidget()
        central.setObjectName("centralRoot")
        body = QVBoxLayout(central)
        body.setContentsMargins(14, 14, 14, 14)
        body.setSpacing(10)

        # 1. QSplitter Vertical Principal (Línea central flexible que divide las secciones)
        self.main_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_vertical_splitter.setObjectName("mainVerticalSplitter")
        self.main_vertical_splitter.setChildrenCollapsible(False)

        # 2. Construimos las dos secciones principales móviles con sus botones integrados en cabecera
        self._build_input_section()    # Sección de Entrada (Superior)
        self._build_library_section()  # Sección de Biblioteca (Inferior)

        # 3. Añadimos los paneles completos al Splitter Vertical
        self.main_vertical_splitter.addWidget(self.input_panel)
        self.main_vertical_splitter.addWidget(self.library_panel)

        # 4. Configuración elástica para el reparto de espacio
        self.main_vertical_splitter.setStretchFactor(0, 1)  # Sección de Entrada
        self.main_vertical_splitter.setStretchFactor(1, 1)  # Sección de Biblioteca

        # 5. Agregamos el splitter vertical directamente al layout principal de la ventana
        body.addWidget(self.main_vertical_splitter, 1)

        # El espaciador elástico absorbe el espacio sobrante al arrastrar hacia abajo
        body.addStretch(0)

        self.central_widget = central
        self.setCentralWidget(central)

        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("statusBar")
        self.setStatusBar(self.status_bar)
        self.last_status = ""
        self._set_status("Listo", timeout=3000)

        self._apply_config()
        self._connect_signals()
        
        # Ambas se inician expandidas visualmente por defecto
        self.input_panel.set_expanded(True)
        self.library_panel.set_expanded(True)
    # --- Construccion UI -------------------------------------------------------------
    def _build_input_section(self) -> None:
        # Creamos el panel de Entrada principal
        self.input_panel = SectionPanel("ENTRADA · EXPLORADOR Y STAGING", initially_expanded=True)
        self.input_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.navigator = FolderNavigator([])
        self.staging = StagingPanel([])

        # SOLUCIÓN 1: Ocultamos el campo redundante de conteo interno ("1 listos") del StagingPanel
        if hasattr(self.staging, 'count_label') and self.staging.count_label:
            self.staging.count_label.setVisible(False)
        elif hasattr(self.staging, 'lbl_count') and self.staging.lbl_count:
            self.staging.lbl_count.setVisible(False)

        # Extraemos o creamos los botones para la cabecera de Entrada
        self.clear_all_btn = None
        self.delete_sel_btn = None
        
        if hasattr(self.staging, 'clear_btn'):
            self.clear_all_btn = self.staging.clear_btn
            if self.clear_all_btn.parentWidget():
                self.clear_all_btn.parentWidget().layout().removeWidget(self.clear_all_btn)
        else:
            self.clear_all_btn = QPushButton("Vaciar todo")
            self.clear_all_btn.setObjectName("btnOutline")
            if hasattr(self.staging, '_on_clear_all'):
                self.clear_all_btn.clicked.connect(self.staging._on_clear_all)

        if hasattr(self.staging, 'delete_btn'):
            self.delete_sel_btn = self.staging.delete_btn
            if self.delete_sel_btn.parentWidget():
                self.delete_sel_btn.parentWidget().layout().removeWidget(self.delete_sel_btn)
        else:
            self.delete_sel_btn = QPushButton("Borrar seleccionadas")
            self.delete_sel_btn.setObjectName("btnOutline")
            if hasattr(self.staging, '_on_delete_selected'):
                self.delete_sel_btn.clicked.connect(self.staging._on_delete_selected)

        # Botón Configuración
        self.settings_btn = QToolButton()
        self.settings_btn.setText("⚙ Config")
        self.settings_btn.setObjectName("btnAccent")
        self.settings_btn.setToolTip("Configuración (config.json)")
        self.settings_btn.clicked.connect(self._open_settings)
        
        # Inyección en la cabecera de Entrada
        if hasattr(self.input_panel, '_header') and self.input_panel._header.layout():
            header_lay = self.input_panel._header.layout()
            header_lay.addWidget(self.clear_all_btn)
            header_lay.addWidget(self.delete_sel_btn)
            header_lay.addWidget(self.settings_btn)
        
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        split_horizontal = QSplitter(Qt.Orientation.Horizontal)
        split_horizontal.addWidget(self.navigator)
        split_horizontal.addWidget(self.staging)
        split_horizontal.setSizes([260, 860])
        split_horizontal.setChildrenCollapsible(False)
        
        input_layout.addWidget(split_horizontal, 1)
        
        self._build_control_bar_wrapper()
        input_layout.addWidget(self.control_bar_container)
        
        self.input_panel.set_body(input_container)

    def _build_control_bar_wrapper(self) -> None:
        self.control_bar_container = QWidget()
        self.control_bar_container.setObjectName("controlBar")
        row = QHBoxLayout(self.control_bar_container)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(8)

        label = QLabel("NOMBRE BASE")
        label.setObjectName("controlLabel")
        row.addWidget(label)

        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("input")
        self.name_edit.setPlaceholderText("Nombre de la canción…")
        self.name_edit.textChanged.connect(self._refresh_process_enabled)
        row.addWidget(self.name_edit, 1)

        self.create_btn = QPushButton("Nueva Carpeta")
        self.create_btn.setObjectName("btnOutline")
        self.create_btn.clicked.connect(self._create_working_folder)
        row.addWidget(self.create_btn)

        self.process_btn = QPushButton("PROCESAR ▸")
        self.process_btn.setObjectName("btnPrimary")
        self.process_btn.clicked.connect(self._on_process)
        row.addWidget(self.process_btn)

        self.control_note = QLabel("")
        self.control_note.setObjectName("mutedLabel")
        row.addWidget(self.control_note)

    def _build_library_section(self) -> None:
        # Creamos el panel de Biblioteca principal
        self.library_panel = SectionPanel("BIBLIOTECA · BASE Y VERSIONES", initially_expanded=True)
        self.library_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.folder_list = FolderListView()
        self.detail = self._make_library_detail()

        # SOLUCIÓN 2: Añadimos los botones "Vaciar todo" y "Borrar seleccionados" a la cabecera de la Biblioteca
        self.library_clear_btn = QPushButton("Vaciar todo")
        self.library_clear_btn.setObjectName("btnOutline")
        self.library_clear_btn.clicked.connect(self._on_library_clear_all)

        self.library_delete_btn = QPushButton("Borrar seleccionadas")
        self.library_delete_btn.setObjectName("btnOutline")
        self.library_delete_btn.clicked.connect(self._on_library_delete_selected)

        # Inyección en la cabecera de la Biblioteca
        if hasattr(self.library_panel, '_header') and self.library_panel._header.layout():
            lib_header_lay = self.library_panel._header.layout()
            lib_header_lay.addWidget(self.library_clear_btn)
            lib_header_lay.addWidget(self.library_delete_btn)
        
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.folder_list)
        split.addWidget(self.detail)
        split.setSizes([260, 860])
        split.setChildrenCollapsible(False)
        self.library_panel.set_body(split)

    def _make_library_detail(self):
        from app.ui.file_table import FileTableView
        table = FileTableView([], sidecar_lookup=None)
        table.model.set_sidecar_name_lookup(None)
        table.clickedFile.connect(self._fill_name_from_file)
        table.activatedFile.connect(self._open_media)
        table.contextMenuRequested.connect(self._library_detail_menu)
        return table
    # MÉTODOS NUEVOS: Acciones de borrado para la carpeta base seleccionada en la Biblioteca
    def _on_library_clear_all(self) -> None:
        """Elimina de forma física todos los archivos de música en la canción seleccionada de la Biblioteca."""
        if not self.detail.model.directory or not self.detail.model.directory.is_dir():
            QMessageBox.information(self, "Nada que vaciar", "Selecciona una carpeta de canción primero.")
            return
            
        ret = QMessageBox.question(
            self, "Confirmar vaciado",
            f"¿Estás seguro de que deseas eliminar TODAS las versiones de la carpeta:\n"
            f"«{self.detail.model.directory.name}»?\nEsta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            try:
                for row in self.detail.model.rows:
                    path = row.get("path")
                    if path and path.is_file():
                        path.unlink()
                self.detail.model.refresh()
                self._show_song_folder(self.detail.model.directory)
                self._set_status("Carpeta de la biblioteca vaciada con éxito.", 4000)
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"No se pudieron eliminar algunos archivos:\n{exc}")

    def _on_library_delete_selected(self) -> None:
        """Elimina físicamente los archivos que el usuario tenga seleccionados en la tabla de la biblioteca."""
        # Se asume que FileTableView o su proxy provee acceso a los índices seleccionados
        indexes = self.detail.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Sin selección", "Selecciona uno o más archivos de la tabla abajo.")
            return

        ret = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Deseas eliminar las {len(indexes)} versiones seleccionadas físicamente?\n"
            f"Esta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            try:
                # Iteramos sobre los índices para obtener las rutas de archivo correspondientes
                paths_to_delete = []
                for idx in indexes:
                    # Si la tabla usa un FilterProxyModel, mapeamos al modelo origen
                    if hasattr(self.detail, 'model') and hasattr(self.detail.model, 'mapToSource'):
                        source_idx = self.detail.model.mapToSource(idx)
                        path = self.detail.model.sourceModel().path_at(source_idx.row())
                    else:
                        path = self.detail.model.path_at(idx.row())
                    if path and path.is_file():
                        paths_to_delete.append(path)

                for p in paths_to_delete:
                    p.unlink()

                if self.detail.model.directory:
                    self._show_song_folder(self.detail.model.directory)
                self._set_status(f"Se eliminaron {len(paths_to_delete)} archivo(s) correctamente.", 4000)
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"No se pudo completar el borrado:\n{exc}")

    def _on_input_toggled(self, expanded: bool) -> None:
        self.main_vertical_splitter.setSizes()

    def _on_library_toggled(self, expanded: bool) -> None:
        self.main_vertical_splitter.setSizes()

    # --- Configuracion aplicada -----------------------------------------------------
    def _apply_config(self) -> None:
        exts = self.config.extensiones_permitidas
        self.navigator.set_extensions(exts)
        self.staging.set_extensions(exts)
        self.detail.set_extensions(exts)

        temp = self.config.carpeta_temporal
        if temp:
            Path(temp).mkdir(parents=True, exist_ok=True)
            self.staging.set_directory(Path(temp))

        self.detail.set_sidecar_lookup(None)
        self.detail.model.set_sidecar_name_lookup(None)

        nav = self.config.raiz_navegacion
        default_nav = (self.config.carpeta_base or Path.home())
        if nav and Path(nav).is_dir():
            self.navigator.set_root(Path(nav))
        else:
            self.navigator.set_root(Path(default_nav) if Path(default_nav).is_dir() else Path.home())

        base = self.config.carpeta_base
        if base and Path(base).is_dir():
            self.folder_list.set_root(Path(base))
            self.detail.set_directory(None)
        else:
            self.folder_list.set_root(Path.home())
            self.detail.set_directory(None)

        self._refresh_counts()
        self._refresh_process_enabled()

        if not base:
            self._set_status("Configura la carpeta base en ⚙ Config.", 6000)

    def _refresh_counts(self) -> None:
        self.input_panel.set_count(f"{self.staging.count()} copias listas")
        if self.detail and self.detail.model and self.detail.model.directory:
            n = len(self.detail.model.rows)
            self.library_panel.set_count(f"{n} versión(es)")
        else:
            self.library_panel.set_count("")

    # --- Senales ----------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self.input_panel.toggled.connect(self._on_input_toggled)
        self.library_panel.toggled.connect(self._on_library_toggled)

        self.folder_list.folderSelected.connect(self._show_song_folder)
        self.folder_list.setRootRequested.connect(self._pick_base_folder)
        self.navigator.copyRequested.connect(self._copy_to_staging)
        self.navigator.fileClicked.connect(self._fill_name_from_file)
        self.navigator.openFile.connect(self._open_media)
        self.navigator.infoMessage.connect(self._set_status)
        self.staging.fileClicked.connect(self._fill_name_from_file)
        self.staging.openFile.connect(self._open_media)
        self.staging.stagingChanged.connect(self._on_staging_changed)
        self.staging.statusMessage.connect(self._set_status)

    def _on_staging_changed(self) -> None:
        self._refresh_counts()
        self._refresh_process_enabled()
    # --- Acciones de fondo ---------------------------------------------------------------
    def _fill_name_from_file(self, path) -> None:
        name = Path(path).stem
        self.name_edit.setText(name)
        self._set_status(f"Archivo: {Path(path).name}", 2500)

    def _copy_to_staging(self, paths) -> None:
        added = self.staging.copy_paths(list(paths))
        if added:
            self._set_status(f"{added} copia(s) agregada(s) al staging.", 4000)

    def _show_song_folder(self, folder: Path) -> None:
        sidecar = Sidecar(folder)
        self.detail.set_sidecar_lookup(sidecar.get_original_ct)
        self.detail.model.set_sidecar_name_lookup(sidecar.get_original_name)
        self.detail.set_directory(folder)
        self._fill_name_from_file(folder)
        n = len(self.detail.model.rows)
        self.library_panel.set_count(f"{n} versión(es)")

    def _open_media(self, path) -> None:
        from app.ui.media_modal import MediaModal
        try:
            modal = MediaModal(Path(path), self)
            modal.exec()
        except Exception as exc:
            logger.error("error al abrir el reproductor de %s: %s", path, exc, exc_info=True)
            QMessageBox.critical(
                self, "Error de reproducción",
                f"No se pudo abrir «{Path(path).name}»:\n{exc}")

    def _library_detail_menu(self, path) -> None:
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        if path is not None:
            act = menu.addAction("▶ Reproducir")
            res = menu.exec(self.cursor().pos())
            if res is act:
                self._open_media(path)
        else:
            menu.addAction("—")

    # --- Carpeta de trabajo ---------------------------------------------------------
    def _create_working_folder(self) -> None:
        base = self.config.carpeta_base
        if not base or not Path(base).is_dir():
            QMessageBox.warning(self, "Sin carpeta base",
                                "Configura la carpeta base en ⚙ Config antes de crear carpetas.")
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Sin nombre", "Escribe el nombre de la canción en 'NOMBRE BASE'.")
            return
        folder = Path(base) / name
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"No se pudo crear la carpeta:\n{exc}")
            return
        self.folder_list.set_root(Path(base))
        self._set_status(f"Carpeta de trabajo: {folder}")
        self._show_song_folder(folder)

    # --- Proceso de musica ----------------------------------------------------------
    def _on_process(self) -> None:
        base = self.config.carpeta_base
        temp = self.config.carpeta_temporal
        name = self.name_edit.text().strip()
        if not base or not Path(base).is_dir():
            QMessageBox.warning(self, "Sin carpeta base", "Configura la carpeta base antes de procesar.")
            return
        if not name:
            QMessageBox.warning(self, "Sin nombre", "Escribe el nombre de la canción antes de procesar.")
            return
        if not temp or not Path(temp).is_dir():
            QMessageBox.warning(self, "Sin staging", "No existe la carpeta temporal.")
            return

        from app import processing
        try:
            plan = processing.build_plan(name, Path(base), Path(temp), self.config.extensiones_permitidas)
        except FileNotFoundError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if plan is None:
            QMessageBox.information(self, "Nada que procesar",
                                    "El staging está vacío. Copia archivos a 'ENTRADA · Staging' primero.")
            return

        if not self._confirm_plan(plan):
            return

        self.process_btn.setEnabled(False)
        self.process_btn.setText("PROCESANDO…")
        QApplication.processEvents()
        try:
            result = processing.execute_plan(plan, self.config.extensiones_permitidas)
        except OSError as exc:
            QMessageBox.critical(self, "Error de proceso", str(exc))
            self.process_btn.setText("PROCESAR ▸")
            self.process_btn.setEnabled(True)
            return

        Path(temp).mkdir(parents=True, exist_ok=True)
        self.staging.set_directory(Path(temp))
        self.folder_list.set_root(Path(base))
        detail_dir = Path(base) / name
        self.detail.set_directory(detail_dir)
        sidecar = Sidecar(detail_dir)
        self.detail.set_sidecar_lookup(sidecar.get_original_ct)
        self.detail.model.set_sidecar_name_lookup(sidecar.get_original_name)
        self._refresh_counts()
        self.process_btn.setText("PROCESAR ▸")
        self.process_btn.setEnabled(True)

    def _confirm_plan(self, plan) -> bool:
        from PyQt6.QtWidgets import QDialogButtonBox, QListWidget
        dlg = QDialog(self)
        dlg.setWindowTitle("Confirmar proceso")
        dlg.setModal(True)
        dlg.resize(480, 440)
        lay = QVBoxLayout(dlg)
        head = QLabel(f"Orden final cronológico en «{plan.song_name}»:")
        head.setObjectName("controlLabel")
        lay.addWidget(head)

        lst = QListWidget()
        for f in plan.files:
            origen = "staging" if f.from_staging else "existente"
            lst.addItem(f"  {f.final_name:44s}  {fsutil.format_timestamp(f.original_ct)}   ({origen})")
        lay.addWidget(lst, 1)

        btns = QDialogButtonBox()
        btns.addButton("Procesar", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        return dlg.exec() == QDialog.DialogCode.Accepted

    def _pick_base_folder(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        start = self.config.carpeta_base or ""
        chosen = QFileDialog.getExistingDirectory(self, "Elegir carpeta base", start)
        if not chosen:
            return
        self.config.carpeta_base = chosen
        Path(chosen).mkdir(parents=True, exist_ok=True)
        temp = self.config.carpeta_temporal
        if temp:
            Path(temp).mkdir(parents=True, exist_ok=True)
            self.staging.set_directory(Path(temp))
        self.folder_list.set_root(Path(chosen))
        self._set_status(f"Carpeta base: {chosen}", 5000)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._apply_config()
            self._set_status("Configuración guardada.", 4000)

    def _set_status(self, text: str, timeout: int = 0) -> None:
        self.last_status = text
        self.status_bar.showMessage(text, timeout or 0)

    def _refresh_process_enabled(self) -> None:
        name_ok = bool(self.name_edit.text().strip())
        base_ok = bool(self.config.carpeta_base)
        staging_ok = self.staging.count() > 0
        self.process_btn.setEnabled(name_ok and base_ok and staging_ok)

    def closeEvent(self, event) -> None: 
        event.accept()

    def showEvent(self, event) -> None: 
        super().showEvent(event)
