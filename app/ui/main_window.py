"""Ventana principal: regiones colapsables, navegador, staging, biblioteca y control."""

from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPushButton, QSplitter, QStatusBar,
                             QToolButton, QVBoxLayout, QWidget)

from app import fsutil
from app import logs
from app.config import ConfigManager
from app.sidecar import Sidecar
from app.ui.navigator import FolderListView, FolderNavigator
from app.ui.panels import SectionPanel
from app.ui.settings_dialog import SettingsDialog
from app.ui.staging import StagingPanel

logger = logs.get_logger("main_window")


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.setWindowTitle("Music-App")
        self.resize(1220, 820)
        self.setMinimumSize(920, 620)

        central = QWidget()
        central.setObjectName("centralRoot")
        body = QVBoxLayout(central)
        body.setContentsMargins(14, 0, 14, 14)
        body.setSpacing(10)

        # 1. Barra superior estática (Logo y Configuración)
        self._build_topbar(body)

        # 2. Un único Splitter Vertical Principal para las dos áreas grandes
        self.main_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_vertical_splitter.setChildrenCollapsible(False)

        # 3. Construimos los tres bloques de la app de forma independiente
        self._build_input_section()
        self._build_control_bar_wrapper() 
        self._build_library_section()

        # 4. Añadimos solo ENTRADA y BIBLIOTECA dentro del Splitter Móvil Vertical
        self.main_vertical_splitter.addWidget(self.input_panel)
        self.main_vertical_splitter.addWidget(self.library_panel)

        # 5. Forzamos los tamaños iniciales del divisor (ENTRADA abre grande por defecto)
        self.main_vertical_splitter.setSizes([450, 250])

        # 6. Agregamos el splitter vertical móvil al diseño de la ventana
        body.addWidget(self.main_vertical_splitter, 1)

        # 7. La barra de control ("NOMBRE BASE") se monta abajo, fija y fuera de los scrolls
        body.addWidget(self.control_bar_container)

        self.central_widget = central
        self.setCentralWidget(central)

        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("statusBar")
        self.setStatusBar(self.status_bar)
        self.last_status = ""
        self._set_status("Listo", timeout=3000)

        self._apply_config()
        self._connect_signals()
        self._compact_input = False
    # --- Construccion UI -------------------------------------------------------------
    def _build_topbar(self, body: QVBoxLayout) -> None:
        bar = QWidget()
        bar.setObjectName("topbar")
        b = QHBoxLayout(bar)
        b.setContentsMargins(18, 10, 18, 10)
        title = QLabel("MI MÚSICA")
        title.setObjectName("topbarTitle")
        b.addWidget(title)
        b.addStretch(1)
        self.settings_btn = QToolButton()
        self.settings_btn.setText("⚙ Config")
        self.settings_btn.setObjectName("btnAccent")
        self.settings_btn.setToolTip("Configuración (config.json)")
        self.settings_btn.clicked.connect(self._open_settings)
        b.addWidget(self.settings_btn)
        body.addWidget(bar)

    def _build_input_section(self) -> None:
        self.input_panel = SectionPanel("ENTRADA · Explorador y Staging", initially_expanded=True)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.navigator = FolderNavigator([])
        self.staging = StagingPanel([])
        split.addWidget(self.navigator)
        split.addWidget(self.staging)
        
        # Mueve de forma automática la barra horizontal a la izquierda
        split.setSizes([260, 960])
        split.setChildrenCollapsible(False)
        self.input_panel.set_body(split)

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
        self.library_panel = SectionPanel("BIBLIOTECA · Base y Versiones", initially_expanded=True)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.folder_list = FolderListView()
        self.detail = self._make_library_detail()
        split.addWidget(self.folder_list)
        split.addWidget(self.detail)
        
        # Mueve la barra horizontal inferior a la izquierda de forma automática
        split.setSizes([260, 960])
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
        self.library_panel.set_count("")
    # --- Senales ----------------------------------------------------------------------
    def _connect_signals(self) -> None:
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
        logger.info("PROCESS: base=%r temp=%r name=%r", base, temp, name)
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
            logger.info("plan generado: %d archivo(s), %d del staging, destino=%s",
                        len(plan.files) if plan else 0,
                        plan.staging_count if plan else 0,
                        plan.target_dir if plan else "-")
        except FileNotFoundError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if plan is None:
            QMessageBox.information(self, "Nada que procesar",
                                    "El staging está vacío. Copia archivos a 'ENTRADA · Staging' primero.")
            return

        if not self._confirm_plan(plan):
            logger.info("proceso cancelado por el usuario")
            return

        self.process_btn.setEnabled(False)
        self.process_btn.setText("PROCESANDO…")
        QApplication.processEvents()
        try:
            result = processing.execute_plan(plan, self.config.extensiones_permitidas)
            logger.info("proceso OK: %s", result)
        except OSError as exc:
            logger.error("error de proceso: %s", exc, exc_info=True)
            QMessageBox.critical(self, "Error de proceso", str(exc))
            self.process_btn.setText("PROCESAR ▸")
            self.process_btn.setEnabled(True)
            return
        # Refrescar UI
        Path(temp).mkdir(parents=True, exist_ok=True)
        self.staging.set_directory(Path(temp))
        self.folder_list.set_root(Path(base))
        detail_dir = Path(base) / name
        self.detail.set_directory(detail_dir)
        sidecar = Sidecar(detail_dir)
        self.detail.set_sidecar_lookup(sidecar.get_original_ct)
        self.detail.model.set_sidecar_name_lookup(sidecar.get_original_name)
        self._refresh_counts()
        self.control_note.setText(f"→ {result['files']} versión(es) en {name}")
        self._set_status(f"Procesadas {result['moved']} nueva(s) versión(es) → {plan.target_dir}", 6000)
        self.process_btn.setText("PROCESAR ▸")
        self.process_btn.setEnabled(True)

    def _confirm_plan(self, plan) -> bool:
        from PyQt6.QtWidgets import QDialogButtonBox, QListWidget, QVBoxLayout

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

        note = QLabel("Se copiará al destino y se limpiará el staging. Los originales jamás se tocan.")
        note.setObjectName("mutedLabel")
        lay.addWidget(note)

        btns = QDialogButtonBox()
        ok = btns.addButton("Procesar", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        return dlg.exec() == QDialog.DialogCode.Accepted

    # --- Utilidades de ventana ---------------------------------------------------------
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
