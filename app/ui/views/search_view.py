"""Vista «Buscar Canción»: módulo en construcción (fase 2).

Buscador de canciones iguales (duplicados) dentro de un universo de canciones.
El algoritmo de comparación queda fuera de este refactor.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SearchView(QWidget):
    """Placeholder elegante mientras se desarrolla el motor de búsqueda."""

    def __init__(self, parent=None):
        super().__init__(parent)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 12)
        lay.setSpacing(10)

        icon = QLabel("🔍")
        icon.setStyleSheet("font-size: 40pt;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)

        title = QLabel("BUSCAR CANCIÓN")
        title.setObjectName("topbarTitle")
        title.setStyleSheet("font-size: 16pt; letter-spacing: 3px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        badge = QLabel("Módulo en construcción")
        badge.setObjectName("welcomeHint")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(badge)

        desc = QLabel(
            "Próximamente: encontrar canciones iguales (duplicados) dentro de tu "
            "biblioteca de forma minimalista y precisa.<br>"
            "El motor de comparación se desarrollará en una fase posterior a este refactor."
        )
        desc.setObjectName("mutedLabel")
        desc.setTextFormat(Qt.TextFormat.RichText)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(desc)

        lay.addStretch(1)
