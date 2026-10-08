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


def _audio_selftest(log) -> int:
    """Autotest headless del motor de audio (MUSICAPP_SELFTEST_AUDIO=1).

    Genera dos WAV identicos, corre el analisis real (librosa) y reporta. Sirve
    para verificar el .exe empaquetado sin interfaz.
    """
    import tempfile

    import numpy as np
    import soundfile as sf

    from app import audio_brain

    ok, why = audio_brain.availability()
    log.info("selftest audio: availability=%s %r", ok, why)
    if not ok:
        print(f"SELFTEST AUDIO: FAIL ({why})", flush=True)
        return 2
    folder = Path(tempfile.mkdtemp(prefix="selftest_audio"))
    sr = 22050
    t = np.arange(sr * 4) / sr
    y = (0.3 * np.sin(2 * np.pi * 440 * t)).astype("float32")
    sf.write(str(folder / "a.wav"), y, sr)
    sf.write(str(folder / "b.wav"), y, sr)
    analysis = audio_brain.analyze_folder(folder, [".wav"])
    profiles = len(analysis.profiles)
    result = "PASS" if profiles == 2 and not analysis.errors else "FAIL"
    log.info("selftest audio: perfiles=%d errores=%d -> %s", profiles, len(analysis.errors), result)
    print(f"SELFTEST AUDIO: {result} perfiles={profiles}", flush=True)
    return 0 if result == "PASS" else 3


def main() -> int:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication

    from app import logs
    from app.config import ConfigManager
    from app.ui.main_window import MainWindow

    root = app_root()
    # Ubicacion fija del log para monitoreo: dist\Music-App\musicapp.log. Incluso al
    # ejecutar desde el codigo fuente (no empaquetado) se escribe en la misma carpeta
    # del .exe de produccion, salvo que esa carpeta no exista aun.
    log_base = root
    if not getattr(sys, "frozen", False):
        dist_log = root / "dist" / "Music-App"
        if dist_log.is_dir():
            log_base = dist_log
    log_path = logs.setup_logging(log_base)
    logs.install_crash_hooks(log_path)
    log = logs.get_logger("main")
    log.info("=== INICIO Music-App ===")
    log.info("raiz de la app: %s | empaquetado: %s", root, bool(getattr(sys, "frozen", False)))
    log.info("log: %s", log_path)
    log.info("python: %s", sys.version)

    if os.environ.get("MUSICAPP_SELFTEST_AUDIO"):
        return _audio_selftest(log)

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

    # Config persistente portable: junto al .exe (o en la raiz del proyecto al correr
    # desde el codigo fuente). El build repone una plantilla con campos vacios si falta,
    # de modo que el usuario configure sus datos desde ⚙ Config.
    config = ConfigManager(root)
    log.info("config %s: carpeta_base=%r temporal=%r raiz_nav=%r", config.path,
             config.carpeta_base, config.carpeta_temporal, config.raiz_navegacion)
    log.info("version %s | tema %s", config.version, config.tema)

    apply_theme(app, "dark" if config.tema == "oscuro" else "light")

    # La app arranca directamente en la vista Inicio (bienvenida en el panel derecho).
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
    # Salida forzada antes del teardown del intérprete: evita el access violation
    # que produce PyQt6 + faulthandler al apagar el hilo watchdog (crash report
    # "dejó de funcionar" al cerrar la app empaquetada). El logging escribe con
    # flush por registro, así que no se pierde ninguna línea.
    os._exit(code)


if __name__ == "__main__":
    sys.exit(main())