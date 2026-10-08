"""Vista «Inicio»: bienvenida minimalista (sustituye al antiguo WelcomeWindow modal)."""

import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from app.config import ConfigManager

_SECTIONS: list[tuple[str, str]] = [
    ("QUÉ ES MUSIC-APP",
     "Gestor de versiones musicales (audio y video) para Windows. Organiza las "
     "grabaciones de cada canción en su propia carpeta, renumerándolas "
     "cronológicamente (<b>Canción_v1.ext</b>, <b>_v2</b> …) conservando siempre la "
     "<b>fecha de creación original</b> de cada archivo. Nunca toca los archivos "
     "originales de origen: solo trabaja con las copias del staging."),
    ("ARQUITECTURA Y DISEÑO",
     "<b>Python 3 + PyQt6</b>, arquitectura en capas sin framework adicional:<br>"
     "• <b>Dominio</b> (<i>app/processing.py, sidecar.py, config.py, fsutil.py</i>): "
     "lógica pura sin Qt, testeable de forma aislada.<br>"
     "• <b>Presentación</b> (<i>app/ui/*</i>): widgets Qt con Qt Model/View "
     "(<i>FileTableModel</i> + <i>FilterProxy</i>), secciones colapsables y "
     "comunicación por señales; <i>MainWindow</i> actúa de orquestador.<br>"
     "• <b>Infraestructura</b> (<i>app/logs.py</i>): logging con watchdog, hooks de "
     "crash y trazas de duración.<br>"
     "Patrón <b>plan-then-execute</b>: <i>build_plan</i> calcula el orden final sin "
     "tocar disco → confirmación del usuario → <i>execute_plan</i> en 4 fases con "
     "reintentos. Persistencia JSON portable: <i>config.json</i> + sidecar "
     "<i>.musicapp.json</i> por canción. Tema QSS claro/oscuro conmutable (luna/sol)."),
    ("CÓMO FUNCIONA",
     "<b>1.</b> ⚙ <b>Config</b>: elige la carpeta base y la raíz de navegación.<br>"
     "<b>2.</b> <b>ENTRADA · Explorador</b>: navega carpetas y copia grabaciones al "
     "<b>staging</b> (también arrastrando desde el Explorador de Windows).<br>"
     "<b>3.</b> <b>Nombre base</b>: escribe el nombre de la canción (o haz clic en "
     "un archivo para autocompletarlo) y pulsa <b>PROCESAR ▸</b>.<br>"
     "<b>4.</b> Revisa el plan cronológico, confirma, y los archivos se fusionan en "
     "la carpeta definitiva v1…vN.<br>"
     "<b>5.</b> <b>BIBLIOTECA</b>: previsualiza (▶), borra o renumera las versiones "
     "de cada canción."),
]


def _card(title: str, body: str) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)

    t = QLabel(title)
    t.setObjectName("welcomeCardTitle")
    t.setWordWrap(True)
    lay.addWidget(t)

    b = QLabel(body)
    b.setObjectName("welcomeBody")
    b.setWordWrap(True)
    b.setTextFormat(Qt.TextFormat.RichText)
    b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lay.addWidget(b)
    return card


class WelcomeView(QWidget):
    """Bienvenida fija dentro del panel derecho (vista por defecto al abrir la app)."""

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)

        title = QLabel("MUSIC-APP")
        title.setObjectName("topbarTitle")
        title.setStyleSheet("font-size: 20pt; letter-spacing: 4px; padding-left: 0;")
        root.addWidget(title)

        subtitle = QLabel("Gestor de versiones musicales · audio y video")
        subtitle.setObjectName("mutedLabel")
        subtitle.setStyleSheet("font-size: 11pt;")
        root.addWidget(subtitle)

        hint = QLabel("Elige una opción del menú lateral para comenzar:  "
                      "🏠 Inicio  ·  🎵 Agrupar Temas  ·  🔍 Buscar Canción")
        hint.setObjectName("welcomeHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        body = QVBoxLayout(inner)
        body.setContentsMargins(0, 4, 0, 4)
        body.setSpacing(12)
        for head, text in _SECTIONS:
            body.addWidget(_card(head, text))
        body.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        version = QLabel(f"Versión {html.escape(config.version)}")
        version.setObjectName("mutedLabel")
        version.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(version)
