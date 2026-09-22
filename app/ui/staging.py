"""Panel de staging (carpeta temporal). Copias seguras + drag & drop desde Explorer."""

import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QMenu, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from app import fsutil
from app import logs
from app.ui.file_table import FileTableView, has_file_payload, urls_from_mime

logger = logs.get_logger("staging")


def unique_target(directory: Path, name: str) -> Path:
    """Nombre unico dentro de `directory` sin pisar archivos existentes."""
    cand = directory / name
    if not cand.exists():
        return cand
    stem, ext = cand.stem, cand.suffix
    i = 2
    while True:
        cand = directory / f"{stem} ({i}){ext}"
        if not cand.exists():
            return cand
        i += 1


class StagingPanel(QWidget):
    """Cuadrante derecho de la fila superior: cola de copias listas para procesar."""

    stagingChanged = pyqtSignal()       # se agregaron/borraron copias
    openFile = pyqtSignal(Path)
    fileClicked = pyqtSignal(Path)
    statusMessage = pyqtSignal(str)

    def __init__(self, extensions: list[str], parent=None):
        super().__init__(parent)
        self.extensions = list(extensions)
        self.directory: Optional[Path] = None

        # CORREGIDO: Rediseño del layout vertical eliminando el espacio del header antiguo
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 12)
        layout.setSpacing(8)

        self.setAcceptDrops(True)

        # CORREGIDO: Se eliminó el layout 'header', los botones físicos y la etiqueta '0 listos'
        self.table = FileTableView(extensions, parent=self)
        self.table.setAcceptDrops(True)
        self.table.accept_file_drops = True
        self.table.viewport().setAcceptDrops(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.table.activatedFile.connect(self.openFile.emit)
        self.table.clickedFile.connect(self.fileClicked.emit)
        self.table.contextMenuRequested.connect(self._show_context_menu)
        self.table.pathsDropped.connect(self._drop_paths)
        self.table.model.modelReset.connect(self._update_empty_state)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("Arrastra archivos aquí\ndesde el Explorador de Windows")
        self.empty_label.setObjectName("mutedLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        self._forwarding_ancestors: set = set()
        self.empty_label.setAcceptDrops(True)
        self.empty_label.installEventFilter(self)
        self._install_drop_forwarders()

        if self.parentWidget() is None:
            QTimer.singleShot(0, self._install_drop_forwarders)

    def _install_drop_forwarders(self) -> None:
        anc = self.parentWidget()
        seen = set()
        while anc is not None:
            seen.add(id(anc))
            if id(anc) not in self._forwarding_ancestors:
                anc.setAcceptDrops(True)
                anc.installEventFilter(self)
                self._forwarding_ancestors.add(id(anc))
            anc = anc.parentWidget()

    # --- Estado --------------------------------------------------------------------
    def set_directory(self, directory: Path) -> None:
        with logs.track(logger, f"staging: set_directory {directory}"):
            self.directory = directory
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
            self.table.set_directory(directory)
            self._update_counts()

    def set_extensions(self, extensions: list[str]) -> None:
        self.extensions = list(extensions)
        self.table.set_extensions(extensions)

    def refresh(self) -> None:
        if self.directory:
            self.table.refresh()
        self._update_counts()

    def count(self) -> int:
        return len(self.table.model.rows)

    def _update_counts(self) -> None:
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        empty = self.count() == 0
        self.empty_label.setVisible(empty)
        self.table.setVisible(not empty)
        if self.directory is None:
            self.empty_label.setText("Arrastra archivos aquí\ndesde el Explorador\n"
                                     "· primero elige la carpeta temporal en ⚙ Configuración ·")
        else:
            self.empty_label.setText("Arrastra archivos aquí\ndesde el Explorador de Windows")

    # --- Drag & drop ----------------------------------------------------------------
    def eventFilter(self, obj, event):  # noqa: N802
        t = event.type()
        if t == QEvent.Type.DragEnter:
            self.dragEnterEvent(event)
            return bool(event.isAccepted())
        if t == QEvent.Type.DragMove:
            self.dragMoveEvent(event)
            return bool(event.isAccepted())
        if t == QEvent.Type.Drop:
            self.dropEvent(event)
            return bool(event.isAccepted())
        return False

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if not self.directory:
            event.ignore()
            return
        if has_file_payload(event.mimeData()):
            event.acceptProposedAction()
        else:
            from app.ui.file_table import _qt_model_display_strings
            names = _qt_model_display_strings(event.mimeData())
            logger.debug("dragEnter panel ignorado: payload sin archivos "
                         "(formats=%r, modeloDisplay=%r)",
                         event.mimeData().formats(), names[:5])
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self.directory and has_file_payload(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        if not self.directory:
            logger.warning("drop ignorado: sin carpeta temporal configurada")
            self.statusMessage.emit("Primero elige la carpeta temporal en ⚙ Configuración.")
            event.ignore()
            return
        try:
            paths = urls_from_mime(event.mimeData())
            logger.info("drop sobre el panel: %d URL(s) en payload -> %d archivo(s)",
                        event.mimeData().urls().__len__(), len(paths))
            event.acceptProposedAction()
        except Exception as exc:  # noqa: BLE001
            logger.error("drop del panel fallo en la preparacion: %s", exc, exc_info=True)
            event.ignore()
            return
        self._drop_paths(paths)
    def _drop_paths(self, paths: list[Path]) -> None:
        if not self.directory:
            logger.warning("drop/copia ignorada: sin carpeta temporal")
            return
        added = 0
        skipped_ext = 0
        skipped_other = 0
        for src in paths:
            if not src.is_file():
                skipped_other += 1
                continue
            if not fsutil.is_allowed(src, self.extensions):
                skipped_ext += 1
                continue
            try:
                self._copy_in(src)
                added += 1
            except OSError as exc:
                logger.error("error al copiar %s al staging: %s", src, exc)
                self.statusMessage.emit(f"No se pudo copiar «{src.name}»: {exc}")
        logger.info("drop: %d agregado(s), %d fuera de extension, %d no archivo (total %d)",
                    added, skipped_ext, skipped_other, len(paths))
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            logger.error("refresh tras drop fallo: %s", exc, exc_info=True)
        if added:
            self.stagingChanged.emit()
        if skipped_ext:
            self.statusMessage.emit(
                f"Ignorados {skipped_ext} archivo(s) fuera de las extensiones permitidas.")

    # --- Copiar ---------------------------------------------------------------------
    def copy_paths(self, sources: list[Path]) -> int:
        if not self.directory or not sources:
            return 0
        added = 0
        for src in sources:
            if src.is_file() and fsutil.is_allowed(src, self.extensions):
                self._copy_in(src)
                added += 1
        logger.info("copy_paths: %d de %d copiados al staging", added, len(sources))
        self.refresh()
        if added:
            self.stagingChanged.emit()
        return added

    def _copy_in(self, src: Path) -> None:
        from PyQt6.QtCore import QEventLoop
        from PyQt6.QtWidgets import QApplication

        dst = unique_target(self.directory, src.name)

        def pump() -> None:
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                                       | QEventLoop.ProcessEventsFlag.ExcludeSocketNotifiers)

        fsutil.copy_file_responsive(src, dst, yield_cb=pump)
        if self.directory is not None:
            fsutil.set_creation_time_windows(dst, fsutil.get_creation_time(src))
        logger.debug("copiado %s -> %s", src, dst)

    # --- Borrar ---------------------------------------------------------------------
    def _delete_selected(self) -> None:
        paths = self.table.selected_paths()
        if not paths:
            self.statusMessage.emit("Selecciona las filas que quieras borrar del staging.")
            return
        logger.info("staging: borrar %d seleccionada(s) -> %s", len(paths),
                    [p.name for p in paths])
        resp = QMessageBox.question(
            self, "Borrar copias del staging",
            f"¿Borrar {len(paths)} copia(s) del staging?\n(Solo se eliminan las copias, "
            "jamás los archivos originales).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes:
            logger.info("staging: borrado cancelado por el usuario")
            return
        failed = []
        for p in paths:
            if not self._unlink_retry(p):
                failed.append(p)
        self._report_delete_result(len(paths), len(failed), failed)

    def _clear_all(self) -> None:
        if self.count() == 0:
            return
        logger.info("staging: vaciar todo (%d copia(s))", self.count())
        resp = QMessageBox.question(
            self, "Vaciar staging",
            "¿Eliminar TODAS las copias del staging?\n(Solo se eliminan las copias, "
            "jamás los archivos originales).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes:
            logger.info("staging: vaciado cancelado por el usuario")
            return
        to_delete = [p for p in self.directory.iterdir()] if self.directory else []
        failed = []
        for p in to_delete:
            if p.is_file() and not self._unlink_retry(p):
                failed.append(p)
        self._report_delete_result(len(to_delete), len(failed), failed)

    def _unlink_retry(self, path: Path, attempts: int = 5, delay_sec: float = 0.15) -> bool:
        for i in range(attempts):
            try:
                path.unlink()
                logger.info("staging: borrado OK %s (intento %d)", path, i + 1)
                return True
            except OSError as exc:
                logger.warning("staging: borrado fallo %s (intento %d): %s", path, i + 1, exc)
                if i >= attempts - 1:
                    return False
                time.sleep(delay_sec)
        return False

    def _report_delete_result(self, total: int, failures: int, failed: list[Path]) -> None:
        self.refresh()
        self.stagingChanged.emit()
        if failures:
            names = ", ".join(p.name for p in failed[:5])
            msg = (f"{failures} de {total} archivo(s) no se pudieron borrar "
                   f"(probablemente están abiertos en el reproductor):\n{names}")
            if len(failed) > 5:
                msg += "…"
            logger.warning("borrado parcial: %d fallidos de %d", failures, total)
            QMessageBox.warning(self, "Borrado incompleto",
                                msg + "\n\nCierra el reproductor de música y vuelve a intentarlo.")
        else:
            logger.info("borrado OK: %d archivo(s)", total)
            self.statusMessage.emit(f"{total} archivo(s) eliminado(s) del staging.")

    # --- Menu contextual -------------------------------------------------------------
    def _show_context_menu(self, path: Optional[Path]) -> None:
        menu = QMenu(self)
        if path is not None:
            act_open = menu.addAction("▶ Reproducir")
            menu.addSeparator()
        act_del = menu.addAction("🗑 Borrar seleccionadas")
        chosen = menu.exec(self.cursor().pos())
        if chosen is act_open:
            self.openFile.emit(path)
        elif chosen is act_del:
            self._delete_selected()
