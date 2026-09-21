"""Ventana modal multimedia: video (MP4) centrado o audio compacto (MP3/WAV).

Degrada con elegancia si el backend multimedia (FFmpeg) no esta disponible.
"""

import hashlib
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt, QTime
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QSlider, QVBoxLayout, QWidget)

from app import logs

logger = logs.get_logger("media_modal")

VIDEO_EXTENSIONS = {".mp4"}


class _WaveformWidget(QWidget):
    """Onda decorativa determinista (generada del contenido del archivo)."""

    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(64)
        seed = hashlib.sha256(str(file_path).encode("utf-8", "ignore")).hexdigest()
        n = len(seed)
        self.bars = [int(seed[(i * 4) % n:((i * 4) % n) + 4], 16) % 70 + 20 for i in range(64)]
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        n = len(self.bars)
        gap = 3
        bw = (w - gap * (n - 1)) / n if n > 1 else w
        mid = h / 2
        pen = QPen(QColor("#7C6CFF"))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QColor("#7C6CFF"))
        for i, b in enumerate(self.bars):
            bh = max(3.0, h * b / 140.0)
            x = i * (bw + gap)
            painter.drawRoundedRect(int(x), int(mid - bh / 2), max(1, int(bw)), int(bh), 2, 2)


class MediaModal(QDialog):
    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.is_video = self.file_path.suffix.lower() in VIDEO_EXTENSIONS
        self.setModal(True)
        self.setWindowTitle(self.file_path.name)
        self._seeking = False
        self._total_ms = 0
        self._expanded_mode = False 
        logger.info("abriendo modal multimedia: %s (video=%s)",
                    self.file_path, self.is_video)

        if self.is_video:
            self.resize(1020, 680)
        else:
            self.resize(450, 185)

        self.setStyleSheet("""
QDialog { background-color: #02123d; }
QLabel { background-color: transparent; color: #E6ECFA; }
#sectionHeaderTitle { color: #FFFFFF; }
#mutedLabel, #secondaryLabel { color: #A9B6D8; }
QSlider::groove:horizontal { background: #243464; height: 6px; border-radius: 3px; }
QSlider::handle:horizontal { background: #FFFFFF; border: 2px solid #3D5AA8; width: 13px; height: 13px; margin: -5px 0; border-radius: 7px; }
QSlider::sub-page:horizontal { background: #3D5AA8; border-radius: 3px; }
QPushButton { background-color: #0F2453; color: #E6ECFA; border: 1px solid #2A3F7A; border-radius: 9px; padding: 7px 12px; font-weight: 700; font-size: 9pt; }
QPushButton:hover { background-color: #163061; }
QPushButton:pressed { background-color: #081638; }
QPushButton:disabled { background-color: #0B1A40; color: #66749C; border-color: #1A2B57; }
QPushButton#btnDanger { background-color: transparent; color: #E5484D; border: 1px solid rgba(229, 72, 77, 0.55); }
QPushButton#btnDanger:hover { background-color: #3A1622; color: #FF6B70; }
""")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel(self.file_path.name)
        title.setObjectName("sectionHeaderTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.error_label = QLabel("")
        self.error_label.setObjectName("mutedLabel")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        if self.is_video:
            self.video_widget = QVideoWidget()
            self.video_widget.setStyleSheet("background: #000000; border-radius: 8px;")
            self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
            layout.addWidget(self.video_widget, 1)
        else:
            self.wave = _WaveformWidget(self.file_path)
            self.wave.setFixedHeight(64)
            layout.addWidget(self.wave)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("secondaryLabel")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.time_label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.slider.sliderReleased.connect(self._seek_to_slider)
        layout.addWidget(self.slider)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addStretch(1)

        # Botón para conmutar Aspect Ratio (Solo visible en videos)
        self.zoom_btn = QPushButton("⛶ Ajustar")
        self.zoom_btn.setObjectName("btnOutline")
        self.zoom_btn.setFixedSize(85, 44)
        self.zoom_btn.clicked.connect(self._toggle_aspect_ratio)
        if not self.is_video:
            self.zoom_btn.setVisible(False)
        controls.addWidget(self.zoom_btn)

        # NUEVO: Botón Retroceder 10 Segundos
        self.back_btn = QPushButton("⏪ -10s")
        self.back_btn.setObjectName("btnOutline")
        self.back_btn.setFixedSize(70, 44)
        self.back_btn.clicked.connect(lambda: self._skip_bytes(-10000))
        controls.addWidget(self.back_btn)

        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("btnOutline")
        self.play_btn.setFixedSize(44, 44)
        self.play_btn.clicked.connect(self._toggle_play)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setObjectName("btnOutline")
        self.stop_btn.setFixedSize(44, 44)
        self.stop_btn.clicked.connect(self._stop)

        # NUEVO: Botón Adelantar 10 Segundos
        self.forward_btn = QPushButton("+10s ⏩")
        self.forward_btn.setObjectName("btnOutline")
        self.forward_btn.setFixedSize(70, 44)
        self.forward_btn.clicked.connect(lambda: self._skip_bytes(10000))
        controls.addWidget(self.forward_btn)

        self.close_btn = QPushButton("❌")
        self.close_btn.setObjectName("btnDanger")
        self.close_btn.setFixedSize(44, 44)
        self.close_btn.clicked.connect(self.reject)
        
        controls.addWidget(self.play_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(self.close_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        # Backend multimedia
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        if self.is_video:
            self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.errorOccurred.connect(self._on_error)
        self.player.mediaStatusChanged.connect(self._on_media_status)

        self.play_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.forward_btn.setEnabled(False)
        self._load_media()

# --- Carga / control -----------------------------------------------------------
    def _load_media(self) -> None:
        logger.info("cargando fuente: %s", self.file_path)
        self.player.setSource(QUrl.fromLocalFile(str(self.file_path)))
        logger.info("setSource enviado")

    # NUEVA FUNCIÓN: Salta el tiempo hacia adelante o atrás controlando los límites
    def _skip_bytes(self, ms_to_skip: int) -> None:
        current_pos = self.player.position()
        new_pos = max(0, min(self._total_ms, current_pos + ms_to_skip))
        logger.info("Salto temporal de %d ms a %d ms", ms_to_skip, new_pos)
        self.player.setPosition(new_pos)
        self.slider.setValue(new_pos)

    def _toggle_aspect_ratio(self) -> None:
        if not self.is_video:
            return
        if self._expanded_mode:
            self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
            self.zoom_btn.setText("⛶ Ajustar")
            self._expanded_mode = False
            logger.info("Modo de aspecto: Original (Barra)")
        else:
            self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            self.zoom_btn.setText("🗗 Original")
            self._expanded_mode = True
            logger.info("Modo de aspecto: Expandido Máximo")

    @staticmethod
    def _format(ms: int) -> str:
        t = QTime(0, 0).addMSecs(ms)
        return t.toString("m:ss") if t.hour() == 0 else t.toString("h:mm:ss")

    def _on_duration(self, ms: int) -> None:
        self._total_ms = ms
        self.slider.setRange(0, max(0, ms))
        self.time_label.setText(f"0:00 / {self._format(ms)}")
        logger.info("duracion cargada: %d ms", ms)

    def _on_position(self, ms: int) -> None:
        if not self._seeking:
            self.slider.setValue(ms)
        self.time_label.setText(f"{self._format(ms)} / {self._format(self._total_ms)}")

    def _seek_to_slider(self) -> None:
        self._seeking = False
        logger.info("seek a %d ms", self.slider.value())
        self.player.setPosition(self.slider.value())

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_btn.setText("▶")
            logger.info("pausa")
        else:
            self.player.play()
            self.play_btn.setText("⏸")
            logger.info("play")

    def _stop(self) -> None:
        logger.info("stop (pausa + rebobinar)")
        self.player.pause()
        self.player.setPosition(0)
        self.slider.setValue(0)
        self.play_btn.setText("▶")

    def _on_media_status(self, status) -> None:
        logger.debug("mediaStatusChanged -> %s", status.name)
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self.play_btn.setEnabled(True)
            self.back_btn.setEnabled(True)
            self.forward_btn.setEnabled(True)

    def _on_error(self, error, error_string) -> None:
        self.play_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.forward_btn.setEnabled(False)
        if error == QMediaPlayer.Error.NoError:
            return
        code = error.name if hasattr(error, "name") else str(error)
        logger.error("QMediaPlayer error %s: %s", code, error_string)
        msg = (f"Error multimedia ({code}).\n{error_string}")
        self.error_label.setText(msg)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._release()
        super().closeEvent(event)

    def reject(self) -> None:
        logger.info("cerrando modal multimedia (pausa; backend se cierra al destruir el player)")
        self._release()
        super().reject()

    def _release(self) -> None:
        try:
            self.player.pause()
        except RuntimeError:
            pass
