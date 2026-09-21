"""Gestor de versiones musicales (audio/video).

Entrada: python main.py
Empaquetado: pyinstaller build.spec
"""

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """Directorio raiz de la app: junto al .exe si esta empaquetada, si no, la raiz del proyecto."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> int:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication

    from app import logs
    from app.config import ConfigManager
    from app.ui.main_window import MainWindow

    root = app_root()
    log_path = logs.setup_logging(root)
    logs.install_crash_hooks(log_path)
    log = logs.get_logger("main")
    log.info("=== INICIO Music-App ===")
    log.info("raiz de la app: %s | empaquetado: %s", root, bool(getattr(sys, "frozen", False)))
    log.info("log: %s", log_path)
    log.info("python: %s", sys.version)

    app = QApplication(sys.argv)
    app.setApplicationName("Music-App")
    app.setOrganizationName("Music-App")
    app.setStyle("Fusion")

    # Actividad de UI para el watchdog + vigila por si el hilo se bloquea
    logs.install_activity_filter(app)
    logs.watchdog_install(threshold_seconds=20.0)
    pulse = QTimer()
    pulse.setInterval(2000)
    pulse.timeout.connect(lambda: logs.note("pulso UI"))
    pulse.start()
    log.info("watchdog y pulso de actividad ACTIVOS (bloqueo > 20s => volcado al log)")

    font = QFont("Segoe UI Variable Text", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    from app.ui.theme import apply_theme

    apply_theme(app)

    # Config persistente: en %APPDATA%/Music-App cuando se esta empaquetado, asi los
    # rebuilds del .exe no borran config.json (migra la legacy de una sola vez).
    config_dir = root
    legacy_cfg = root / "config.json"
    if getattr(sys, "frozen", False):
        user_dir = Path(os.environ.get("APPDATA") or str(Path.home())) / "Music-App"
        user_dir.mkdir(parents=True, exist_ok=True)
        if not (user_dir / "config.json").exists() and legacy_cfg.exists():
            import shutil

            try:
                shutil.copyfile(legacy_cfg, user_dir / "config.json")
                log.info("config migrada de %s a %s", legacy_cfg, user_dir / "config.json")
            except OSError as exc:
                log.warning("no se pudo migrar la config: %s", exc)
        config_dir = user_dir

    config = ConfigManager(config_dir)
    log.info("config carpeta_base=%r temporal=%r raiz_nav=%r",
             config.carpeta_base, config.carpeta_temporal, config.raiz_navegacion)

    window = MainWindow(config)
    window.show()
    log.info("ventana principal mostrada")

    # Modo auto-salida para verificacion automatizada del .exe empaquetado
    exit_ms = os.environ.get("MUSICAPP_EXIT_MS")
    if exit_ms:
        log.info("auto-salida MUSICAPP_EXIT_MS=%s", exit_ms)
        QTimer.singleShot(int(exit_ms), app.quit)

    code = app.exec()
    log.info("=== FIN Music-App (codigo %s) ===", code)
    return code


if __name__ == "__main__":
    sys.exit(main())