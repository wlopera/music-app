"""Shell de la ventana principal: cabecera + menú lateral + vistas + pie.

La ventana es frameless: la cabecera hace de título arrastrable (doble clic =
maximizar) y el redimensionado se resuelve con un QSizeGrip en el pie (NUNCA
sobrescribir `nativeEvent` en PyQt6: provoca un access violation en Windows).
El contenido real vive en `app/ui/views/*`, conmutado por un QStackedWidget.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QStackedWidget,
                             QVBoxLayout, QWidget, QMainWindow)

from app import logs
from app.config import ConfigManager
from app.ui import theme
from app.ui.footer import WindowFooter
from app.ui.header import WindowHeader
from app.ui.log_panel import LogPanel
from app.ui.sidebar import Sidebar
from app.ui.views import AgruparView, SearchView, WelcomeView

logger = logs.get_logger("main_window")

_VIEWS: tuple[str, ...] = ("Inicio", "Agrupar Temas", "Buscar Canciones")


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.setWindowTitle("Music-App")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        # Dimensiones compactas optimizadas
        self.resize(1120, 720)
        self.setMinimumSize(820, 520)

        central = QWidget()
        central.setObjectName("centralRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Cabecera ------------------------------------------------------
        self.header = WindowHeader()
        root.addWidget(self.header)

        # --- Cuerpo: sidebar + vistas --------------------------------------
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        self.sidebar = Sidebar()
        body_lay.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("viewStack")
        self.welcome_view = WelcomeView(config)
        self.agrupar = AgruparView(config)
        self.search_view = SearchView(config)
        self.stack.addWidget(self.welcome_view)   # índice 0: vista por defecto
        self.stack.addWidget(self.agrupar)        # índice 1
        self.stack.addWidget(self.search_view)    # índice 2
        body_lay.addWidget(self.stack, 1)

        root.addWidget(body, 1)

        # --- Panel de Registros y Trazas (colapsable) ----------------------
        self.log_panel = LogPanel()
        root.addWidget(self.log_panel)

        # --- Pie -----------------------------------------------------------
        self.footer = WindowFooter()
        self.footer.set_version(config.version)
        root.addWidget(self.footer)

        self.setCentralWidget(central)

        # --- Conexiones ----------------------------------------------------
        self.sidebar.navigated.connect(self._navigate)
        self.header.themeRequested.connect(self._toggle_theme)
        self.header.settingsRequested.connect(self._open_settings)
        self.header.minimizeRequested.connect(self.showMinimized)
        self.header.maximizeRequested.connect(self._toggle_maximize)
        self.header.closeRequested.connect(self.close)
        self.agrupar.statusMessage.connect(self._set_status)
        self.search_view.statusMessage.connect(self._set_status)

        self.last_status = ""
        self.header.sync_theme_btn(theme.current_mode())
        # Estado inicial: el último mensaje de la vista (p.ej. falta de carpeta
        # base) o "Listo"
        self._set_status(self.agrupar.last_status or "Listo", 5000)
        self._navigate(0, announce=False)

    # --- Navegación ---------------------------------------------------------
    def _navigate(self, index: int, announce: bool = True) -> None:
        if not 0 <= index < self.stack.count():
            logger.warning("navegación a índice inválido: %s", index)
            return
        self.stack.setCurrentIndex(index)
        self.sidebar.set_current(index)
        logger.info("vista: %s", _VIEWS[index])
        if announce:
            self._set_status(f"Vista: {_VIEWS[index]}", 2500)

    # --- Acciones comunes (cabecera) ----------------------------------------
    def _toggle_theme(self) -> None:
        mode = theme.toggle_theme(QApplication.instance())
        self.config.tema = mode  # persiste la elección en config.json
        self.header.sync_theme_btn(mode)
        logger.info("tema cambiado a %s", mode)
        self._set_status("Tema oscuro activado." if mode == "dark" else "Tema claro activado.", 3000)

    def _open_settings(self) -> None:
        from app.ui.settings_dialog import SettingsDialog
        logger.info("abrir dialogo de configuracion")
        logs.note("abrir configuracion")
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.agrupar.apply_config()
            self._set_status("Configuración guardada.", 4000)
            logger.info("configuracion guardada y aplicada")
        else:
            logger.info("configuracion descartada")

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _set_status(self, text: str, timeout: int = 0) -> None:
        self.last_status = text
        self.footer.set_status(text, timeout)

    def closeEvent(self, event) -> None:
        event.accept()

    def showEvent(self, event) -> None:
        super().showEvent(event)