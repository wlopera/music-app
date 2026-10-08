"""Cabecera de la ventana: nombre de la app, botones comunes y controles de ventana.

La ventana es frameless, así que esta barra también hace de título arrastrable
(doble clic = maximizar/restaurar).
"""

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from app.ui import icons

_APP_TITLE = "Music-App"


class WindowHeader(QWidget):
    """Barra superior fija: 🎵 Music-App | botones comunes | min/max/close."""

    themeRequested = pyqtSignal()
    settingsRequested = pyqtSignal()
    minimizeRequested = pyqtSignal()
    maximizeRequested = pyqtSignal()
    closeRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("windowHeader")
        self.setFixedHeight(46)
        self._dragging = False
        self._drag_offset = QPoint()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 5, 6, 5)
        lay.setSpacing(6)

        mark = QLabel("🎵")
        mark.setObjectName("headerMark")
        lay.addWidget(mark)

        title = QLabel(_APP_TITLE)
        title.setObjectName("headerTitle")
        lay.addWidget(title)

        lay.addStretch(1)

        # --- Botones comunes de la aplicación -------------------------------
        self.theme_btn = QToolButton()
        self.theme_btn.setObjectName("headerButton")
        self.theme_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.theme_btn.setFixedWidth(32)
        self.theme_btn.clicked.connect(self.themeRequested)
        lay.addWidget(self.theme_btn)
        self.sync_theme_btn("light")

        self.settings_btn = QToolButton()
        self.settings_btn.setObjectName("headerButton")
        self.settings_btn.setText("⚙")
        self.settings_btn.setToolTip("Configuración (config.json)")
        self.settings_btn.setFixedWidth(32)
        self.settings_btn.clicked.connect(self.settingsRequested)
        lay.addWidget(self.settings_btn)

        # --- Controles de ventana ------------------------------------------
        for text, slot, name in (
            ("—", self.minimizeRequested, "btnWinMin"),
            ("□", self.maximizeRequested, "btnWinMax"),
            ("✕", self.closeRequested, "btnWinClose"),
        ):
            btn = QToolButton()
            btn.setText(text)
            btn.setObjectName(name)
            btn.setFixedSize(38, 34)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

    def sync_theme_btn(self, mode: str) -> None:
        """Actualiza el icono y la ayuda del botón de tema según el modo activo."""
        self.theme_btn.setIcon(icons.theme_icon(mode, 16))
        if mode == "dark":
            self.theme_btn.setToolTip("Cambiar a tema claro (sol)")
        else:
            self.theme_btn.setToolTip("Cambiar a tema oscuro (luna)")

    # --- Arrastre de la ventana (titlebar manual) -------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            cursor = event.globalPosition().toPoint()
            if win.isMaximized():
                # Restaurar manteniendo el cursor sobre la misma proporción horizontal
                geo = win.frameGeometry()
                rx = (cursor.x() - geo.x()) / max(1, geo.width())
                win.showNormal()
                geo = win.frameGeometry()
                geo.moveLeft(int(cursor.x() - rx * geo.width()))
                geo.moveTop(int(cursor.y() - self.height() // 2))
                win.setGeometry(geo)
                geo = win.frameGeometry()
            else:
                geo = win.frameGeometry()
            self._drag_offset = cursor - geo.topLeft()
            self._dragging = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximizeRequested.emit()
        super().mouseDoubleClickEvent(event)
