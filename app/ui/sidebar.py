"""Menú lateral (sidebar) de navegación entre vistas del QStackedWidget."""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui import icons

_ITEMS: tuple[tuple[str, str], ...] = (
    ("🏠", "Inicio"),
    ("🎵", "Agrupar Temas"),
    ("🔍", "Buscar Canciones"),
)


class Sidebar(QWidget):
    """Columna izquierda con las tres secciones de la aplicación."""

    navigated = pyqtSignal(int)  # indice de la vista solicitada

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(216)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 14, 12, 14)
        lay.setSpacing(4)

        heading = QHBoxLayout()
        mark = QLabel("MENÚ")
        mark.setObjectName("sidebarHeading")
        heading.addWidget(mark)
        heading.addStretch(1)
        lay.addLayout(heading)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self._buttons: list[QPushButton] = []
        for index, (emoji, text) in enumerate(_ITEMS):
            if text == "Agrupar Temas":
                btn = QPushButton(f"  {text}")
                btn.setIcon(icons.music_note_icon("dark", 18))
                btn.setIconSize(QSize(18, 18))
            else:
                btn = QPushButton(f"{emoji}   {text}")
            btn.setCheckable(True)
            btn.setObjectName("navItem")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(text)
            btn.clicked.connect(lambda _=False, i=index: self.navigated.emit(i))
            self._group.addButton(btn, index)
            self._buttons.append(btn)
            lay.addWidget(btn)

        lay.addStretch(1)

        self.set_current(0)

    def set_current(self, index: int) -> None:
        """Marca como activo el botón de la vista mostrada (señal silenciosa)."""
        btn = self._group.button(index)
        if btn and not btn.isChecked():
            btn.setChecked(True)

    def sync_theme(self, mode: str) -> None:
        """Actualiza el icono dinámico de la nota musical según el tema."""
        if len(self._buttons) > 1:
            self._buttons[1].setIcon(icons.music_note_icon(mode, 18))
