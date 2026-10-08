"""Pie de la ventana: mensajes de estado (izquierda) · autor y versión (derecha)."""

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizeGrip, QWidget


class WindowFooter(QWidget):
    """Barra inferior fija: estado de la app + firma «William Lopera · vX»."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("windowFooter")
        self.setFixedHeight(30)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 3, 14, 3)
        lay.setSpacing(10)

        self.status_label = QLabel("")
        self.status_label.setObjectName("footerStatus")
        self.status_label.setWordWrap(False)
        lay.addWidget(self.status_label)

        lay.addStretch(1)

        self.version_label = QLabel("")
        self.version_label.setObjectName("welcomeFooter")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.version_label)

        # Grip de redimensionado para la ventana frameless (esquina inferior
        # derecha). Widget QSizeGrip puro de Qt: seguro, sin nativeEvent.
        self.grip = QSizeGrip(self)
        self.grip.setObjectName("footerGrip")
        self.grip.setFixedSize(16, 16)
        lay.addWidget(self.grip)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.status_label.clear)

    def set_version(self, version: str) -> None:
        self.version_label.setText(f"William Lopera · v{version}")

    def set_status(self, text: str, timeout: int = 0) -> None:
        """Muestra el mensaje; si timeout > 0 (ms) lo borra automáticamente."""
        self._timer.stop()
        self.status_label.setText(text)
        if timeout:
            self._timer.start(timeout)
