"""Analizador de audio en hilo de fondo (threading plano, sin QThread).

Se usa un `threading.Thread` normal —NO un `QThread` de Qt— y las señales se
emiten hacia un `QObject` que vive en el hilo GUI de Qt, que las entrega de forma
segura (queued). Así la interfaz se mantiene fluida durante el análisis de una
biblioteca grande y no se atan hilos nativos de Qt a librerías de audio.
"""

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from app import logs

logger = logs.get_logger("search_worker")


class SearchAnalyzer(QObject):
    """Ejecuta `audio_brain.analyze_folder` en un hilo de fondo."""

    progress = pyqtSignal(int, int, str)   # hechos, total, nombre actual
    analyzed = pyqtSignal(object)          # app.audio_brain.Analysis
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: threading.Thread | None = None

    def start(self, folder: str, extensions: list[str]) -> None:
        """Lanza el análisis en un hilo de fondo."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, args=(folder, extensions),
            name="search-analyzer", daemon=True)
        self._thread.start()

    def _run(self, folder: str, extensions: list[str]) -> None:
        from app import audio_brain
        try:
            analysis = audio_brain.analyze_folder(
                Path(folder),
                extensions,
                progress_cb=lambda done, total, name: self.progress.emit(done, total, name))
        except Exception as exc:  # noqa: BLE001
            logger.error("fallo en el análisis: %s", exc)
            self.failed.emit(str(exc))
            return
        logger.info("análisis en hilo: %d perfil(es), %d error(es), %d ignorado(s)",
                    len(analysis.profiles), len(analysis.errors), len(analysis.ignored))
        self.analyzed.emit(analysis)