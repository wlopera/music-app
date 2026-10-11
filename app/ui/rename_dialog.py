"""Dialogo modal para renombrar archivos o carpetas con validacion y soporte de sidecar."""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QVBoxLayout)

from app import logs
from app.sidecar import Sidecar

logger = logs.get_logger("rename_dialog")

_INVALID_CHARS = set('<>:"/\\|?*')


class RenameDialog(QDialog):
    """Diálogo modal para renombrar un archivo o carpeta."""

    def __init__(self, target_path: Path, parent=None):
        super().__init__(parent)
        self.target_path = Path(target_path)
        self.new_path: Optional[Path] = None

        is_file = self.target_path.is_file()
        title = "Renombrar archivo" if is_file else "Renombrar carpeta"
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(480, 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        tipo_texto = "archivo" if is_file else "carpeta"
        lbl = QLabel(f"Introduce el nuevo nombre para el {tipo_texto}:\n<b>{self.target_path.name}</b>")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self.name_edit = QLineEdit(self.target_path.name)
        self.name_edit.setObjectName("input")
        # Si es un archivo, pre-seleccionamos solo el nombre sin la extensión para facilitar la edición
        if is_file and self.target_path.suffix:
            stem_len = len(self.target_path.stem)
            self.name_edit.setSelection(0, stem_len)
        else:
            self.name_edit.selectAll()
        layout.addWidget(self.name_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setObjectName("btnOutline")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Renombrar")
        save_btn.setObjectName("btnPrimary")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _on_save(self) -> None:
        raw_name = self.name_edit.text().strip()
        if not raw_name:
            QMessageBox.warning(self, "Nombre vacío", "Debes ingresar un nombre válido.")
            return

        # Si el usuario no escribió extensión en un archivo, conservamos la extensión original
        if self.target_path.is_file() and not Path(raw_name).suffix and self.target_path.suffix:
            raw_name = f"{raw_name}{self.target_path.suffix}"

        if any(c in _INVALID_CHARS for c in raw_name):
            QMessageBox.warning(
                self, "Nombre inválido",
                "El nombre no puede contener ninguno de los siguientes caracteres:\n< > : \" / \\ | ? *"
            )
            return

        if raw_name == self.target_path.name:
            self.reject()
            return

        destination = self.target_path.parent / raw_name
        if destination.exists():
            QMessageBox.warning(
                self, "Elemento existente",
                f"Ya existe un elemento llamado «{raw_name}» en esta ubicación."
            )
            return

        try:
            self.target_path.rename(destination)
            # Actualizamos el sidecar .musicapp.json si existe en la carpeta
            sidecar = Sidecar(destination.parent)
            if sidecar.exists():
                sidecar.rename_entry(self.target_path.name, destination.name)

            self.new_path = destination
            logger.info("renombrado OK: %s -> %s", self.target_path, destination)
            self.accept()
        except OSError as exc:
            logger.error("error al renombrar %s: %s", self.target_path, exc)
            QMessageBox.critical(
                self, "Error al renombrar",
                f"No se pudo renombrar:\n{exc}"
            )


def prompt_rename(target_path: Path, parent=None) -> Optional[Path]:
    """Abre el diálogo de renombrado y retorna el nuevo Path si fue exitoso, o None."""
    dlg = RenameDialog(target_path, parent=parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.new_path
    return None
