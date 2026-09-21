"""Dialogo de configuracion (config.json)."""

from pathlib import Path

from PyQt6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from app.config import ConfigManager


def _browse(parent, edit: QLineEdit, dialog_cb) -> None:
    resp = dialog_cb(parent, edit.text())
    if resp:
        edit.setText(str(resp))


class SettingsDialog(QDialog):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Configuración · Music-App")
        self.setModal(True)
        self.resize(580, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)

        self.base_edit, base_btn = self._row(
            config.carpeta_base or "",
            lambda p, s: QFileDialog.getExistingDirectory(p, "Carpeta base", s))
        self.temp_edit, temp_btn = self._row(
            config.carpeta_temporal or "",
            lambda p, s: QFileDialog.getExistingDirectory(p, "Carpeta temporal", s))
        self.nav_edit, nav_btn = self._row(
            config.raiz_navegacion or "",
            lambda p, s: QFileDialog.getExistingDirectory(p, "Raíz de búsqueda", s))

        form.addRow("Carpeta base", self._wrap(self.base_edit, base_btn))
        form.addRow("Carpeta temporal", self._wrap(self.temp_edit, temp_btn))
        form.addRow("Extensiones permitidas", self._extensions_edit())
        form.addRow("Raíz de búsqueda", self._wrap(self.nav_edit, nav_btn))
        layout.addLayout(form)

        hint = QLabel("Carpeta temporal vacía = automática: carpeta_base\\_staging\n"
                      "Raíz de búsqueda vacía = inicio en 'Este equipo'.")
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        save_btn = QPushButton("Guardar")
        save_btn.setObjectName("btnPrimary")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setObjectName("btnOutline")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

    # --- Helpers UI ---------------------------------------------------------------
    def _row(self, initial: str, dialog_cb):
        edit = QLineEdit(initial)
        edit.setObjectName("input")
        btn = QPushButton("…")
        btn.setObjectName("btnOutline")
        btn.setMaximumWidth(40)
        btn.clicked.connect(lambda: _browse(self, edit, dialog_cb))
        return edit, btn

    def _wrap(self, edit: QLineEdit, btn: QPushButton) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(edit, 1)
        row.addWidget(btn)
        return row

    def _extensions_edit(self):
        self.ext_edit = QLineEdit(", ".join(self.config.extensiones_permitidas))
        self.ext_edit.setObjectName("input")
        self.ext_edit.setPlaceholderText(".mp3, .wav, .mp4")
        return self.ext_edit

    # --- Guardar -------------------------------------------------------------------
    def _save(self) -> None:
        base = self.base_edit.text().strip()
        temp = self.temp_edit.text().strip()
        nav = self.nav_edit.text().strip()
        exts = [e.strip() for e in self.ext_edit.text().split(",") if e.strip()]

        if base and not Path(base).is_dir():
            QMessageBox.warning(self, "Ruta inválida", "La carpeta base no existe.")
            return
        if exts and not all(e.lower().startswith(".") for e in exts):
            QMessageBox.warning(self, "Extensiones",
                                "Las extensiones deben llevar punto: .mp3, .wav, .mp4")
            return

        self.config.carpeta_base = base
        self.config.carpeta_temporal = temp
        self.config.raiz_navegacion = nav
        if exts:
            self.config.extensiones_permitidas = exts
        self.accept()