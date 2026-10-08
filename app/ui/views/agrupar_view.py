"""Vista «Agrupar Temas»: secciones ENTRADA y BIBLIOTECA (logica extraida de MainWindow).

El shell (MainWindow) solo conmuta vistas; aqui vive todo el control de canciones:
explorador, staging, nombre base, proceso plan-then-execute y biblioteca.
Los mensajes de estado se emiten via `statusMessage` hacia el pie de la ventana.
"""

import time
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QSizePolicy, QSplitter,
                             QStyle, QToolButton, QVBoxLayout, QWidget)

from app import fsutil
from app import logs
from app.config import ConfigManager
from app.sidecar import Sidecar
from app.ui.navigator import FolderListView, FolderNavigator
from app.ui.panels import SectionPanel
from app.ui.staging import StagingPanel

logger = logs.get_logger("agrupar_view")


class AgruparView(QWidget):
    """Panel derecho: gestor completo de versiones musicales."""

    statusMessage = pyqtSignal(str, int)  # texto, timeout en ms (0 = permanente)

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.last_status = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # QSplitter vertical principal (linea central flexible entre secciones)
        self.main_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_vertical_splitter.setObjectName("mainVerticalSplitter")
        self.main_vertical_splitter.setChildrenCollapsible(False)

        self._build_input_section()    # Seccion de Entrada (superior)
        self._build_library_section()  # Seccion de Biblioteca (inferior)

        self.main_vertical_splitter.addWidget(self.input_panel)
        self.main_vertical_splitter.addWidget(self.library_panel)
        self.main_vertical_splitter.setStretchFactor(0, 1)
        self.main_vertical_splitter.setStretchFactor(1, 1)

        lay.addWidget(self.main_vertical_splitter, 1)
        lay.addStretch(0)

        self.apply_config()
        self._connect_signals()

        # Ambas se inician expandidas visualmente por defecto
        self.input_panel.set_expanded(True)
        self.library_panel.set_expanded(True)

    # --- Construccion UI -------------------------------------------------------------
    def _build_input_section(self) -> None:
        self.input_panel = SectionPanel("ENTRADA · EXPLORADOR Y STAGING", initially_expanded=True)
        self.input_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.navigator = FolderNavigator([])
        self.staging = StagingPanel([])

        # Ocultamos el campo redundante de conteo interno si existe en el subpanel
        if hasattr(self.staging, 'count_label') and self.staging.count_label:
            self.staging.count_label.setVisible(False)
        elif hasattr(self.staging, 'lbl_count') and self.staging.lbl_count:
            self.staging.lbl_count.setVisible(False)

        # Iconos estandar integrados en el motor grafico nativo de PyQt6
        style = self.style()
        icon_vaciar = style.standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton)
        icon_borrar = style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon)

        # Boton Vaciar Todo (Entrada) - Vinculacion directa al metodo del staging corregido
        self.clear_all_btn = QToolButton()
        self.clear_all_btn.setIcon(icon_vaciar)
        self.clear_all_btn.setObjectName("btnIconHeader")
        self.clear_all_btn.setToolTip("Vaciar todo el Staging")
        self.clear_all_btn.clicked.connect(self.staging._clear_all)

        # Boton Borrar Seleccionadas (Entrada) - Vinculacion directa al metodo del staging corregido
        self.delete_sel_btn = QToolButton()
        self.delete_sel_btn.setIcon(icon_borrar)
        self.delete_sel_btn.setObjectName("btnIconHeader")
        self.delete_sel_btn.setToolTip("Borrar archivos seleccionados del Staging")
        self.delete_sel_btn.clicked.connect(self.staging._delete_selected)

        # Inyeccion ordenada en el extremo derecho del encabezado de la seccion de Entrada
        # (los botones comunes de la app viven ahora en la cabecera de la ventana)
        if hasattr(self.input_panel, '_header') and self.input_panel._header.layout():
            header_lay = self.input_panel._header.layout()
            header_lay.addWidget(self.clear_all_btn)
            header_lay.addWidget(self.delete_sel_btn)

        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        split_horizontal = QSplitter(Qt.Orientation.Horizontal)
        split_horizontal.addWidget(self.navigator)
        split_horizontal.addWidget(self.staging)

        # Tamanos explicitos en pixeles al divisor horizontal [Navegador, Staging]
        split_horizontal.setSizes([400, 600])
        split_horizontal.setChildrenCollapsible(False)

        input_layout.addWidget(split_horizontal, 1)

        # Barra de control de Nombre Base integrada al pie del area movil
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

    def _refresh_process_enabled(self) -> None:
        """Ubicado estrategicamente aqui para evitar excepciones de inicializacion asincrona."""
        name_ok = bool(self.name_edit.text().strip())
        base_ok = bool(self.config.carpeta_base)
        staging_ok = self.staging.count() > 0
        self.process_btn.setEnabled(name_ok and base_ok and staging_ok)

    def _build_library_section(self) -> None:
        self.library_panel = SectionPanel("BIBLIOTECA · BASE Y VERSIONES", initially_expanded=True)
        self.library_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.folder_list = FolderListView()
        self.detail = self._make_library_detail()

        style = self.style()
        icon_vaciar = style.standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton)
        icon_borrar = style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon)

        # Boton Vaciar Todo (Biblioteca) - Vinculado a la purga de la carpeta fisica de canciones
        self.library_clear_btn = QToolButton()
        self.library_clear_btn.setIcon(icon_vaciar)
        self.library_clear_btn.setObjectName("btnIconHeader")
        self.library_clear_btn.setToolTip("Eliminar todas las versiones de esta canción de la Biblioteca")
        self.library_clear_btn.clicked.connect(self._on_library_clear_all)

        # Boton Borrar Seleccionadas (Biblioteca) - Vinculado a la eliminacion selectiva de la tabla
        self.library_delete_btn = QToolButton()
        self.library_delete_btn.setIcon(icon_borrar)
        self.library_delete_btn.setObjectName("btnIconHeader")
        self.library_delete_btn.setToolTip("Eliminar las versiones seleccionadas de la Biblioteca")
        self.library_delete_btn.clicked.connect(self._on_library_delete_selected)

        # Boton Renumerar (Biblioteca) - Reordena v1..vN de la carpeta base y ajusta
        # el .musicapp.json (entrada por archivo vivo) SIN necesitar staging.
        self.library_renumber_btn = QToolButton()
        self.library_renumber_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.library_renumber_btn.setObjectName("btnIconHeader")
        self.library_renumber_btn.setToolTip("Renumerar v1..vN (Biblioteca) y ajustar el .musicapp.json")
        self.library_renumber_btn.clicked.connect(self._on_library_renumber)

        # Inyeccion ordenada en el extremo derecho del encabezado de la seccion de Biblioteca
        if hasattr(self.library_panel, '_header') and self.library_panel._header.layout():
            lib_header_lay = self.library_panel._header.layout()
            lib_header_lay.addWidget(self.library_clear_btn)
            lib_header_lay.addWidget(self.library_delete_btn)
            lib_header_lay.addWidget(self.library_renumber_btn)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.folder_list)
        split.addWidget(self.detail)

        # Tamanos explicitos en pixeles al divisor horizontal [Carpetas, Tabla]
        split.setSizes([300, 700])
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

    def _on_input_toggled(self, expanded: bool) -> None:
        """Maneja el colapso y expansion elastica del panel de Entrada."""
        logger.info("entrada %s", "expandida" if expanded else "colapsada")
        if expanded:
            self.main_vertical_splitter.setSizes([350, 350])
        else:
            self.main_vertical_splitter.setSizes([0, 700])

    def _on_library_toggled(self, expanded: bool) -> None:
        """Maneja el colapso y expansion elastica del panel de Biblioteca."""
        logger.info("biblioteca %s", "expandida" if expanded else "colapsada")
        if expanded:
            self.main_vertical_splitter.setSizes([350, 350])
        else:
            self.main_vertical_splitter.setSizes([700, 0])

    def _refresh_counts(self) -> None:
        """Satisface las llamadas de inicializacion y refresca el estado del boton procesar."""
        self._refresh_process_enabled()

    # --- Configuracion aplicada -----------------------------------------------------
    def apply_config(self) -> None:
        with logs.track(logger, "apply_config"):
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

        if not base:
            self._set_status("Configura la carpeta base en ⚙ Config.", 6000)

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
        logger.debug("staging cambiado: %d archivo(s)", self.staging.count())
        self._refresh_counts()

    def _on_library_clear_all(self) -> None:
        """Elimina de forma fisica todos los archivos de musica en la carpeta de cancion seleccionada."""
        if not self.detail.model.directory or not self.detail.model.directory.is_dir():
            QMessageBox.information(self, "Nada que vaciar", "Selecciona una carpeta de canción primero.")
            return

        logger.info("biblioteca: VACIAR carpeta %s (%d archivo(s))",
                    self.detail.model.directory, len(self.detail.model.rows))
        ret = QMessageBox.question(
            self, "Confirmar vaciado",
            f"¿Estás seguro de que deseas eliminar TODAS las versiones de la carpeta:\n"
            f"«{self.detail.model.directory.name}»?\nEsta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            logger.info("biblioteca: vaciado cancelado por el usuario")
            return
        with logs.track(logger, f"vaciar {len(self.detail.model.rows)} archivo(s)"):
            try:
                for row in self.detail.model.rows:
                    path = row.get("path")
                    if path and path.is_file():
                        path.unlink()
                        logger.debug("  borrado %s", path)
                self._auto_renumber_library()
                self.detail.model.refresh()
                self._show_song_folder(self.detail.model.directory)
                self._set_status("Carpeta de la biblioteca vaciada con éxito.", 4000)
            except Exception as exc:
                logger.error("error al vaciar la biblioteca: %s", exc, exc_info=True)
                QMessageBox.critical(self, "Error", f"No se pudieron eliminar algunos archivos:\n{exc}")

    def _on_library_delete_selected(self) -> None:
        """Elimina fisicamente los archivos que el usuario tenga seleccionados en la tabla de la biblioteca."""
        t0 = time.monotonic()
        indexes = self.detail.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Sin selección", "Selecciona uno o más archivos de la tabla abajo.")
            return
        logger.info("biblioteca: BORRAR %d seleccionado(s)", len(indexes))
        logs.note("biblioteca: borrar seleccion (confirmacion)")

        ret = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Deseas eliminar las {len(indexes)} versiones seleccionadas físicamente?\n"
            f"Esta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            logger.info("biblioteca: borrado cancelado por el usuario")
            return

        try:
            paths_to_delete = []
            for idx in indexes:
                if hasattr(self.detail, 'model') and hasattr(self.detail.model, 'mapToSource'):
                    source_idx = self.detail.model.mapToSource(idx)
                    path = self.detail.model.sourceModel().path_at(source_idx.row())
                else:
                    path = self.detail.model.path_at(idx.row())
                if path and path.is_file():
                    paths_to_delete.append(path)
            logger.info("biblioteca: %d archivo(s) confirmado(s) -> %s",
                        len(paths_to_delete), [p.name for p in paths_to_delete])
            logs.note("biblioteca: borrando archivos")

            for p in paths_to_delete:
                t = time.monotonic()
                p.unlink()
                logger.info("  biblioteca: borrado OK %s (%.1fms)", p,
                            (time.monotonic() - t) * 1000)

            res = self._auto_renumber_library()

            logger.info("biblioteca: refrescando vista tras borrar")
            logs.note("biblioteca: refrescar despues de borrar")
            if self.detail.model.directory:
                self._show_song_folder(self.detail.model.directory)
            if res and res["renombrados"]:
                self._set_status(
                    f"Se eliminaron {len(paths_to_delete)} archivo(s) y se renumeró "
                    f"la carpeta (v1 = más viejo → vN = más nuevo).", 5000)
            else:
                self._set_status(f"Se eliminaron {len(paths_to_delete)} archivo(s) correctamente.", 4000)
            logger.info("biblioteca: borrado completado (%d archivo(s), %.1fms)",
                        len(paths_to_delete), (time.monotonic() - t0) * 1000)
        except Exception as exc:
            logger.error("biblioteca: fallo al borrar: %s", exc, exc_info=True)
            QMessageBox.critical(self, "Error", f"No se pudo completar el borrado:\n{exc}")

    def _on_library_renumber(self) -> None:
        """Renumera la carpeta base seleccionada (v1..vN por fecha original) y ajusta
        el `.musicapp.json`, limpiando las entradas de archivos ya borrados."""
        if not self.detail.model.directory or not self.detail.model.directory.is_dir():
            QMessageBox.information(self, "Sin carpeta",
                                    "Selecciona una carpeta de canción de la Biblioteca primero.")
            return

        folder = self.detail.model.directory
        logger.info("biblioteca: RENUMERAR carpeta %s (%d archivo(s))",
                    folder, len(self.detail.model.rows))
        ret = QMessageBox.question(
            self, "Confirmar renumeración",
            f"¿Renumerar las versiones v1..vN de «{folder.name}» por fecha original\n"
            f"y ajustar el .musicapp.json? (Se omiten archivos ya borrados.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            logger.info("biblioteca: renumeracion cancelada por el usuario")
            return

        try:
            from app import processing
            result = processing.renumber_target_folder(folder, self.config.extensiones_permitidas)
            logs.note("biblioteca: renumerar ejecutado")
            if self.detail.model.directory:
                self._show_song_folder(self.detail.model.directory)
            self._set_status(
                f"Renumeradas {result['total']} versión(es), {result['renombrados']} renombrada(s).",
                5000)
            logger.info("biblioteca: renumeracion OK: %s", result)
        except Exception as exc:
            logger.error("biblioteca: fallo al renumerar: %s", exc, exc_info=True)
            QMessageBox.critical(self, "Error", f"No se pudo renumerar:\n{exc}")

    def _auto_renumber_library(self):
        """Tras borrar en la Biblioteca, renumera la carpeta base seleccionada
        (v1..vN por fecha original, mas viejo -> mas nuevo) y ajusta el .musicapp.json."""
        folder = self.detail.model.directory
        if not folder or not folder.is_dir():
            return None
        try:
            from app import processing
            result = processing.renumber_target_folder(folder, self.config.extensiones_permitidas)
            if result["renombrados"]:
                logger.info("biblioteca: auto-renumeracion de %s (%d renombrado(s))",
                            folder.name, result["renombrados"])
            return result
        except Exception as exc:
            logger.error("biblioteca: auto-renumeracion fallo: %s", exc, exc_info=True)
            return None

    def _open_media(self, path) -> None:
        from app.ui.media_modal import MediaModal
        t0 = time.monotonic()
        logger.info("abrir media: %s", path)
        logs.note("abrir media")
        try:
            # El preview se abre con show() (NO exec()): un bucle de eventos anidado
            # con video FFmpeg activo provoca un cuelgue del hilo grafico al salir.
            # La modalidad de ventana bloquea la main window igual que un modal real.
            # La preview crea y destruye su PROPIO reproductor al cerrar (teardown
            # sincrono), liberando el archivo para poder borrarlo o renombrarlo despues.
            modal = MediaModal(Path(path), self)
            modal.setWindowModality(Qt.WindowModality.ApplicationModal)
            modal.show()
            self._media_preview = modal  # evita recoleccion; se destruye solo al cerrar
            logger.info("preview abierta (%s) en %.1fms", Path(path).name,
                        (time.monotonic() - t0) * 1000)
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

    def _fill_name_from_file(self, path) -> None:
        name = Path(path).stem
        self.name_edit.setText(name)
        logger.debug("nombre base desde archivo %s", name)
        self._set_status(f"Archivo: {Path(path).name}", 2500)

    def _copy_to_staging(self, paths) -> None:
        added = self.staging.copy_paths(list(paths))
        if added:
            self._set_status(f"{added} copia(s) agregada(s) al staging.", 4000)

    def _show_song_folder(self, folder: Path) -> None:
        with logs.track(logger, f"mostrar carpeta {folder}"):
            sidecar = Sidecar(folder)
            self.detail.set_sidecar_lookup(sidecar.get_original_ct)
            self.detail.model.set_sidecar_name_lookup(sidecar.get_original_name)
            self.detail.set_directory(folder)
            self._fill_name_from_file(folder)
            n = len(self.detail.model.rows)
            self.library_panel.set_count(f"{n} versión(es)")

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
        logger.info("crear carpeta de trabajo: %s", folder)
        logs.note("crear carpeta de trabajo")
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("no se pudo crear la carpeta %s: %s", folder, exc)
            QMessageBox.critical(self, "Error", f"No se pudo crear la carpeta:\n{exc}")
            return
        self.folder_list.set_root(Path(base))
        self._set_status(f"Carpeta de trabajo: {folder}")
        self._show_song_folder(folder)
        logger.info("carpeta de trabajo lista: %s", folder)

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

        logger.info("proceso: '%s' (base=%s, staging=%s)", name, base, temp)
        logs.note("proceso: construir plan")

        from app import processing
        try:
            plan = processing.build_plan(name, Path(base), Path(temp), self.config.extensiones_permitidas)
        except FileNotFoundError as exc:
            logger.error("proceso: carpeta inexistente: %s", exc)
            QMessageBox.critical(self, "Error", str(exc))
            return

        if plan is None:
            QMessageBox.information(self, "Nada que procesar",
                                    "El staging está vacío. Copia archivos a 'ENTRADA · Staging' primero.")
            return

        logger.info("proceso: plan listo (%d versiones), pidiendo confirmacion", len(plan.files))
        logs.note("proceso: confirmar plan")
        if not self._confirm_plan(plan):
            logger.info("proceso: cancelado por el usuario")
            return

        logs.note("proceso: ejecutar plan")
        self.process_btn.setEnabled(False)
        self.process_btn.setText("PROCESANDO…")
        QApplication.processEvents()
        try:
            result = processing.execute_plan(plan, self.config.extensiones_permitidas)
        except OSError as exc:
            logger.error("proceso: error de sistema: %s", exc, exc_info=True)
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
        logger.info("proceso: FIN -> %s (resultado=%s)", detail_dir, result)

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
        logger.info("carpeta base seleccionada: %s", chosen)
        logs.note("seleccionar carpeta base")
        self.config.carpeta_base = chosen
        Path(chosen).mkdir(parents=True, exist_ok=True)
        temp = self.config.carpeta_temporal
        if temp:
            Path(temp).mkdir(parents=True, exist_ok=True)
            self.staging.set_directory(Path(temp))
        self.folder_list.set_root(Path(chosen))
        self._set_status(f"Carpeta base: {chosen}", 5000)

    def _set_status(self, text: str, timeout: int = 0) -> None:
        """Guarda el ultimo mensaje y lo reenvia al pie de la ventana (shell)."""
        self.last_status = text
        self.statusMessage.emit(text, timeout)
