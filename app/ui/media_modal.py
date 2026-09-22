"""Ventana de previsualizacion multimedia: reproductor DEDICADO por preview (no global).

El preview se abre con show() (NO exec()): un solapamiento anidado con video FFmpeg
activo provoca un cuelgue del hilo grafico al salir del bucle. Al cerrar se destruye
el reproductor de forma SINCRONA, liberando el descriptor del archivo para permitir
borrarlo o renombrarlo a continuacion.
"""

import time
from pathlib import Path
from PyQt6.QtCore import QTime, QUrl, Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, 
                             QSlider, QVBoxLayout, QWidget, QApplication)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from app import logs

logger = logs.get_logger("media_modal")


class MediaModal(QDialog):
    """Ventana de previsualizacion con atmosfera oscura cinematografica.

    Crea su PROPIO QMediaPlayer/QAudioOutput y los destruye al cerrar: es la regla de
    robustez del plan (§6). Un player persistente mantiene el archivo abierto
    (WinError 32 al borrar) y stop()/setSource(QUrl()) bloquean la UI en Windows.
    El cierre es SINCRONO y todos sus pasos quedan trazados en el log.
    """

    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        t0 = time.monotonic()
        logger.info("modal: ABRIR %s (%d bytes)",
                    file_path, file_path.stat().st_size if file_path.is_file() else -1)
        logs.note("modal: abrir reproductor")
        # Reproductor dedicado: se destruye junto al diálogo para liberar el backend
        # (FFmpeg) y el descriptor del archivo reproducido.
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        
        self.setWindowTitle(f"Reproduciendo: {file_path.name}")
        self.resize(1020, 680)
        self.setMinimumSize(640, 480)
        # Barra de titulo con los botones nativos minimizar/maximizar/restaurar (□❐).
        # Un QDialog por defecto NO los muestra: se anaden via WindowFlags.
        self.setWindowFlags(self.windowFlags() |
                            Qt.WindowType.WindowSystemMenuHint |
                            Qt.WindowType.WindowMinimizeButtonHint |
                            Qt.WindowType.WindowMaximizeButtonHint)

        # Atmósfera cinematográfica oscura original (#02123d)
        self.setStyleSheet("""
            QDialog { background-color: #02123d; color: #f1f5f9; }
            QLabel { color: #cbd5e1; font-family: 'Segoe UI', Arial; font-size: 13px; }
            QPushButton { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 6px; color: #f8fafc; font-weight: bold; padding: 6px 12px; min-width: 60px; }
            QPushButton:hover { background-color: #1e293b; border-color: #334155; }
            QPushButton:pressed { background-color: #020617; }
            QSlider::groove:horizontal { border: 1px solid #1e293b; height: 6px; background: #0f172a; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #2563eb; border-radius: 3px; }
            QSlider::handle:horizontal { background: #f8fafc; border: 1px solid #cbd5e1; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }
        """)

        # Layout Principal Vertical
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # Importación tardía para evitar colisiones
        from PyQt6.QtMultimediaWidgets import QVideoWidget
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #000000; border-radius: 8px;")
        self.main_layout.addWidget(self.video_widget, 1)

        self._build_controls()
        
        # Conectamos las señales del reproductor global de forma segura
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.progress_slider.sliderMoved.connect(self._on_slider_moved)

        # Direccionamos el video hacia nuestro widget e iniciamos la reproducción
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setSource(QUrl.fromLocalFile(str(file_path)))
        self.media_player.play()
        logger.info("modal: cargado y PLAY en %.1fms", (time.monotonic() - t0) * 1000)

    def _build_controls(self) -> None:
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 0)
        self.main_layout.addWidget(self.progress_slider)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        self.btn_scale = QPushButton("⛶ Ajustar")
        self.btn_scale.clicked.connect(self._toggle_aspect_ratio)
        controls_layout.addWidget(self.btn_scale)

        self.btn_back = QPushButton("⏪ -10s")
        self.btn_back.clicked.connect(self._skip_backward)
        controls_layout.addWidget(self.btn_back)

        self.btn_play = QPushButton("⏸ Pausa")
        self.btn_play.clicked.connect(self._toggle_playback)
        controls_layout.addWidget(self.btn_play)

        self.btn_forward = QPushButton("+10s ⏩")
        self.btn_forward.clicked.connect(self._skip_forward)
        controls_layout.addWidget(self.btn_forward)

        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setToolTip("Silenciar")
        self.btn_mute.setFixedWidth(44)
        self.btn_mute.clicked.connect(self._toggle_mute)
        controls_layout.addWidget(self.btn_mute)

        controls_layout.addStretch(1)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("color: #000000; font-weight: bold;")
        controls_layout.addWidget(self.lbl_time)

        self.main_layout.addLayout(controls_layout)

    def _format_time(self, ms: int) -> str:
        seconds = (ms // 1000) % 60
        minutes = (ms // 60000) % 60
        return f"{minutes:02d}:{seconds:02d}"

    def _on_position_changed(self, position: int) -> None:
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(position)
        self.lbl_time.setText(f"{self._format_time(position)} / {self._format_time(self.media_player.duration())}")

    def _on_duration_changed(self, duration: int) -> None:
        self.progress_slider.setRange(0, duration)
        self.lbl_time.setText(f"{self._format_time(self.media_player.position())} / {self._format_time(duration)}")

    def _on_slider_moved(self, position: int) -> None:
        self.media_player.setPosition(position)

    def _toggle_playback(self) -> None:
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.btn_play.setText("▶ Play")
            logger.info("modal: PAUSA de %s", self.file_path.name)
        else:
            self.media_player.play()
            self.btn_play.setText("⏸ Pausa")
            logger.info("modal: PLAY de %s", self.file_path.name)
        logs.note("modal: boton play/pausa")

    def _toggle_aspect_ratio(self) -> None:
        current = self.video_widget.aspectRatioMode()
        if current == Qt.AspectRatioMode.KeepAspectRatio:
            self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)
            self.btn_scale.setText("🗗 Original")
        else:
            self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
            self.btn_scale.setText("⛶ Ajustar")

    def _skip_forward(self) -> None:
        self.media_player.setPosition(min(self.media_player.duration(), self.media_player.position() + 10000))

    def _skip_backward(self) -> None:
        self.media_player.setPosition(max(0, self.media_player.position() - 10000))

    def _toggle_mute(self) -> None:
        # OJO: NO usar media_player.setMuted() mientras el video suena (bloquea el
        # hilo grafico con el backend FFmpeg). El silencio via audio_output es seguro.
        muted = not self.audio_output.isMuted()
        self.audio_output.setMuted(muted)
        self.btn_mute.setText("🔇" if muted else "🔊")
        self.btn_mute.setToolTip("Activar sonido" if muted else "Silenciar")
        logger.info("modal: audio %s de %s", "SILENCIADO" if muted else "ACTIVADO",
                    self.file_path.name)
        logs.note("modal: boton silencio")

    def closeEvent(self, event) -> None:
        """Cierre por la X: teardown sincrono y liberacion del descriptor del archivo."""
        logger.info("modal: cierre por boton X")
        event.ignore()
        self.setVisible(False)  # Desaparicion visual inmediata
        self._release_and_close()

    def reject(self) -> None:
        """Tecla Escape o cancelacion: mismo ciclo de cierre."""
        logger.info("modal: cierre por Esc/reject")
        self.setVisible(False)
        self._release_and_close()

    def _release_and_close(self) -> None:
        """Teardown SINCRONO del reproductor al cerrar el preview.

        CRITICO: el preview se abre con show() (no exec()), asi el cierre ocurre
        dentro del bucle de eventos principal. Destruir aqui el reproductor apaga el
        backend FFmpeg, suelta el descriptor del archivo y permite borrarlo despues.
        Un cierre diferido (QTimer.singleShot) o un bucle anidado con un player de
        video activo provocaba un cuelgue del hilo grafico en este entorno.
        """
        t0 = time.monotonic()
        logger.info("modal: CERRANDO %s", self.file_path.name)
        logs.note("modal: cerrando (desconectar senales)")
        try:
            # 1. Desconexion limpia de senales locales para evitar fugas de memoria
            try: self.media_player.positionChanged.disconnect(self._on_position_changed)
            except Exception: pass
            try: self.media_player.durationChanged.disconnect(self._on_duration_changed)
            except Exception: pass
            try: self.progress_slider.sliderMoved.disconnect(self._on_slider_moved)
            except Exception: pass

            # 2. Desvinculamos el output grafico nativo para que deje de enviar fotogramas
            logs.note("modal: cerrando (setVideoOutput None)")
            t = time.monotonic()
            self.media_player.setVideoOutput(None)
            logger.info("  setVideoOutput(None) en %.1fms", (time.monotonic() - t) * 1000)

            # 3. Regla del proyecto (plan §6): NUNCA stop()/setSource(QUrl()) con medios
            #    reales (bloquean la UI). La pausa corta el audio al instante.
            logs.note("modal: cerrando (pause)")
            t = time.monotonic()
            self.media_player.pause()
            logger.info("  pause() en %.1fms", (time.monotonic() - t) * 1000)

            # 4. Destruccion del reproductor + flush: el backend se apaga YA dentro de
            #    este mismo turno y se libera el descriptor del archivo reproducido.
            logs.note("modal: destruyendo reproductor")
            t = time.monotonic()
            self.media_player.deleteLater()
            self.audio_output.deleteLater()
            QApplication.processEvents()
            logger.info("  deleteLater + flush en %.1fms", (time.monotonic() - t) * 1000)

            # 5. Cierre visual del dialogo
            self.deleteLater()
            self.hide()
            logger.info("modal: CERRADA (%s) en %.1fms", self.file_path.name,
                        (time.monotonic() - t0) * 1000)

        except Exception as exc:
            logger.error("modal: ERROR en cierre: %s", exc, exc_info=True)
            self.hide()
