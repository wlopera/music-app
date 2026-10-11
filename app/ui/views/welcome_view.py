"""Vista «Inicio»: bienvenida minimalista (sustituye al antiguo WelcomeWindow modal)."""

import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from app.config import ConfigManager

_SECTIONS: list[tuple[str, str]] = [
    ("MUSIC-APP · GUÍA RÁPIDA",
     "Gestor de versiones musicales para Windows. La aplicación se organiza en "
     "<b>cuatro secciones</b> que abres desde el <b>menú lateral izquierdo</b>. "
     "Antes de empezar, configura tus carpetas en <b>⚙ Config</b> (arriba a la "
     "derecha). El botón <b>luna/sol</b> de la cabecera alterna entre tema "
     "<b>oscuro y claro</b>."),
    ("🏠  INICIO — esta pantalla",
     "Es el punto de partida: muestra esta guía y te orienta. Desde aquí no se "
     "modifica ningún archivo. Usa el menú lateral para ir a <b>Navegador</b>, "
     "<b>Agrupar Temas</b> o <b>Buscar Canciones</b>. Abajo a la derecha verás la <b>versión</b> de la app."),
    ("📁  NAVEGADOR — explorador multimedia y gestión de archivos",
     "Explorador de dos paneles especializado en tu colección de audio y video con "
     "estilo Windows Explorer:<br>"
     "• <b>Árbol de Directorios (Izquierda)</b>: Navegación jerárquica fluida entre carpetas y unidades físicas.<br>"
     "• <b>Tabla de Contenido (Derecha)</b>: Visualiza Nombre, Tamaño, Tipo y Fecha con ordenación por columnas.<br>"
     "• <b>Filtrado Inteligente con Comodines</b>: Filtra archivos en tiempo real por texto o patrones glob "
     "(por ejemplo <code>*.mp3</code>, <code>demo*.mpe</code> o listas como <code>*.mp3, *.wav</code>).<br>"
     "• <b>Modo Multimedia / Todos los Archivos</b>: Botón en barra y ajuste <code>only_music</code> en configuración "
     "para alternar entre ver solo audio/video o todos los archivos de tu sistema.<br>"
     "• <b>Papelera de Reciclaje de Windows</b>: Lo que eliminas se envía a la Papelera de reciclaje de Windows, "
     "<b>garantizando que siempre puedas recuperarlo</b> en cualquier momento.<br>"
     "• <b>Menú Contextual y Atajos</b>: Clic derecho o teclado para reproducir, renombrar (<b>F2</b>), "
     "cortar (<b>Ctrl+X</b>), copiar (<b>Ctrl+C</b>), pegar (<b>Ctrl+V</b>), nueva carpeta (<b>Ctrl+Shift+N</b>) "
     "y enviar a papelera (<b>Supr</b>).<br>"
     "• <b>Audición Inmediata</b>: Haz <b>doble clic</b> sobre un archivo de audio o video para reproducirlo al instante "
     "con el reproductor multimedia integrado.<br>"
     "• <b>Drag & Drop</b>: Arrastra y suelta archivos cómodamente entre carpetas o hacia otras aplicaciones."),
    ("🎵  AGRUPAR TEMAS — ordena las versiones de una canción",
     "Reúne las grabaciones de una misma canción en una carpeta y las renumera "
     "cronológicamente (<b>Canción_v1.ext</b>, <b>_v2</b> …) conservando siempre la "
     "<b>fecha de creación original</b> de cada archivo.<br>"
     "<b>1.</b> ⚙ <b>Config</b>: elige la <i>carpeta base</i> y la <i>raíz de navegación</i>.<br>"
     "<b>2.</b> <b>ENTRADA · Explorador</b>: navega y copia las grabaciones al "
     "<b>staging</b> (también arrastrando desde el Explorador de Windows).<br>"
     "<b>3.</b> Escribe el <b>Nombre base</b> de la canción (o haz clic en un "
     "archivo para autocompletarlo) y pulsa <b>PROCESAR ▸</b>.<br>"
     "<b>4.</b> Revisa el plan cronológico, confirma y se crearán las versiones "
     "<b>v1…vN</b> en la carpeta definitiva.<br>"
     "<b>5.</b> <b>BIBLIOTECA</b>: previsualiza (▶), borra o renumera las versiones "
     "de cada canción.<br>"
     "<i>Los archivos originales de origen nunca se tocan: solo se trabaja con las "
     "copias del staging.</i>"),
    ("🔍  BUSCAR CANCIONES — detecta y organiza canciones repetidas",
     "Escanea una carpeta y agrupa automáticamente las pistas con la misma "
     "composición o huella acústica en subcarpetas separadas (<b>carpeta_1</b>, "
     "<b>carpeta_2</b>…), incluso si fueron interpretadas en diferentes tonos o tonalidades, "
     "manteniendo intactas las canciones únicas en la raíz.<br>"
     "<b>1.</b> Pulsa <b>Examinar…</b> y selecciona la carpeta que deseas estudiar.<br>"
     "<b>2.</b> Ajusta la <b>Sensibilidad</b>: <i>Flexible</i> (97.0%), <b>Recomendado</b> (98.5%) "
     "o <i>Estricto</i> (99.0%, ideal para maquetas y tomas alternativas).<br>"
     "<b>3.</b> Pulsa <b>Analizar Canciones</b> para procesar el audio con aceleración "
     "multinúcleo adaptable a 1 o múltiples CPUs (formatos <i>.mp3, .wav, .opus, .flac, .ogg, .aiff, .m4a</i>; "
     "hasta 150 MB por pista, con confirmación inteligente para lotes grandes de más de 100 archivos).<br>"
     "<b>4.</b> Revisa los grupos y las canciones únicas: pulsa <b>▶</b> o haz <b>doble clic</b> "
     "en cualquier fila para escuchar la canción con el reproductor minimalista integrado.<br>"
     "<b>5.</b> Puedes pulsar <b>Copiar Plan</b> para copiar el reporte de coincidencias o "
     "<b>Limpiar</b> para reiniciar la vista.<br>"
     "<b>6.</b> Pulsa <b>Mover Canciones</b>: traslada de forma segura solo las pistas duplicadas "
     "a sus subcarpetas correspondientes. <i>Las canciones únicas permanecen siempre en la raíz.</i>"),
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

        subtitle = QLabel("Gestor de versiones musicales · audio/video")
        subtitle.setObjectName("mutedLabel")
        subtitle.setStyleSheet("font-size: 11pt;")
        root.addWidget(subtitle)

        hint = QLabel("Elige una opción del menú lateral para comenzar:  "
                      "🏠 Inicio  ·  📁 Navegador  ·  🎵 Agrupar Temas  ·  🔍 Buscar Canciones")
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
