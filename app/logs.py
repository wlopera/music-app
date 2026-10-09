"""Logging central de Music-App: archivo junto al .exe, watchdog y hooks de errores.

* write `musicapp.log` en la raiz de la app (junto al .exe si esta empaquetada).
* Traza la actividad de la UI via event-filter + pulso: si el hilo grafico deja de
  responder N segundos, el watchdog vuelca el traceback de todos los hilos al log
  para localizar exactamente donde se quedo bloqueado.
* Captura excepciones Python y mensajes Qt a archivo (en un .exe windowed no hay
  consola; este es el unico sitio donde quedan visibles).
"""

import faulthandler
import logging
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

_LOG_FILE_NAME = "musicapp.log"
_HEARTBEAT = {"ts": 0.0, "label": "inicio"}
_fault_file: Optional[object] = None
_watchdog_thread: Optional[threading.Thread] = None
_CURRENT_LOG_PATH: Optional[Path] = None


def current_log_path() -> Optional[Path]:
    """Ruta al archivo activo de logs (None si aun no se ha inicializado)."""
    return _CURRENT_LOG_PATH


def log_path_for(base_dir: Path) -> Path:
    return Path(base_dir) / _LOG_FILE_NAME


def setup_logging(base_dir: Path) -> Path:
    """Configura el logger raiz 'musicapp' y devuelve la ruta del archivo de log."""
    global _CURRENT_LOG_PATH
    base_dir = Path(base_dir)
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    path = log_path_for(base_dir)
    _CURRENT_LOG_PATH = path
    root = logging.getLogger("musicapp")
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s [%(name)s] %(message)s",
                            datefmt="%H:%M:%S")
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if not getattr(sys, "frozen", False):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    note("logging iniciado")
    return path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"musicapp.{name}")


def note(label: str) -> None:
    """Marca actividad del hilo principal (para el watchdog)."""
    _HEARTBEAT["ts"] = time.monotonic()
    _HEARTBEAT["label"] = label


@contextmanager
def track(logger: logging.Logger, label: str, level: int = logging.INFO) -> Iterator[None]:
    """Trazado de un proceso: registra el 'inicio', espera y registra el 'fin' con duracion.

    Uso (en frontend y backend):
        with logs.track(logger, "borrar archivo X"):
            ...
    Si ocurre una excepcion, se registra el tiempo parcial antes de propagarla.
    """
    start = time.monotonic()
    logger.log(level, ">> %s ...inicio", label)
    try:
        yield
    except BaseException:
        logger.log(level, ">> %s ...ERROR a los %.3fs", label, time.monotonic() - start)
        raise
    else:
        logger.log(level, ">> %s ...fin (%.3fs)", label, time.monotonic() - start)


def elapsed_ms(start: float) -> float:
    """Milisegundos transcurridos desde `start` (sirve para tiempos parciales)."""
    return (time.monotonic() - start) * 1000.0


def install_crash_hooks(log_path: Path) -> None:
    """Excepciones Python + mensajes Qt + crashes nativos -> archivo de log."""
    global _fault_file

    def excepthook(etype, exc, tb):
        get_logger("hooks").critical("EXCEPCION NO CAPTURADA",
                                     exc_info=(etype, exc, tb))

    sys.excepthook = excepthook

    try:
        from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

        def qt_handler(kind, _context, message):
            rec = get_logger("qt")
            if kind == QtMsgType.QtDebugMsg:
                rec.debug("%s", message)
            elif kind == QtMsgType.QtInfoMsg:
                rec.info("%s", message)
            elif kind == QtMsgType.QtWarningMsg:
                rec.warning("%s", message)
            elif kind == QtMsgType.QtCriticalMsg:
                rec.critical("%s", message)
            else:
                rec.error("%s", message)

        qInstallMessageHandler(qt_handler)
    except Exception:
        pass

    try:
        _fault_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=_fault_file, all_threads=True)
    except OSError:
        _fault_file = None


def watchdog_install(threshold_seconds: float = 20.0, poll_seconds: float = 4.0) -> None:
    """Vigila el hilo grafico y vuelca tracebacks al log si deja de responder."""
    global _watchdog_thread
    if _watchdog_thread is not None:
        return
    stamps = _HEARTBEAT

    def run() -> None:
        log = get_logger("watchdog")
        while True:
            time.sleep(poll_seconds)
            elapsed = time.monotonic() - stamps["ts"]
            if elapsed <= threshold_seconds:
                continue
            log.critical(
                "POSIBLE BLOQUEO DE LA UI: sin actividad hace %.1fs "
                "(ultima accion: %s). Traceback:",
                elapsed, stamps["label"])
            if _fault_file is not None:
                try:
                    faulthandler.dump_traceback(file=_fault_file, all_threads=True)
                    _fault_file.flush()
                except Exception:
                    pass
            else:
                faulthandler.dump_traceback(all_threads=True)
            # while la UI siga parada, seguimos avisando cada poll
            next_warn = time.monotonic() + poll_seconds
            while True:
                time.sleep(poll_seconds)
                if time.monotonic() - stamps["ts"] <= threshold_seconds:
                    break
                now = time.monotonic()
                if now >= next_warn:
                    log.critical("UI sigue bloqueada (%s): %.1fs sin actividad.", stamps["label"],
                                 time.monotonic() - stamps["ts"])
                    if _fault_file is not None:
                        try:
                            faulthandler.dump_traceback(file=_fault_file, all_threads=True)
                            _fault_file.flush()
                        except Exception:
                            pass
                    next_warn = now + poll_seconds * 3

    _watchdog_thread = threading.Thread(target=run, name="watchdog", daemon=True)
    _watchdog_thread.start()


def install_activity_filter(app):
    """Instala un event-filter que marca actividad de la UI (para el watchdog)."""
    from PyQt6.QtCore import QObject

    class _ActivityFilter(QObject):
        def eventFilter(self, _obj, event):  # noqa: N802
            note(f"evento {event.type().name if hasattr(event.type(), 'name') else event.type()}")
            return False

    filt = _ActivityFilter()
    app.installEventFilter(filt)
    return filt