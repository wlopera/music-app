"""Smoke test de la ventana modal multimedia (Fase 4).

Nota: en esta maquina el backend multimedia de Qt (ffmpeg/windows) se bloquea en
stop()/setSource(QUrl()) y deja el archivo abierto hasta el cierre del proceso.
El codigo de la app NUNCA llama a stop()/unload por API: pausa y deja que el
QMediaPlayer se destruya con el dialogo. El test verifica construccion, carga,
play/pause/stop-boton y cierre sin colgarse. Se usa la plataforma real de Windows
(el backend se deadlocka con "offscreen"). Nota importante: los handles se liberan
en procesos sanos; aqui el temp dir no se puede borrar -> ignore_cleanup_errors.
"""
import math
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_SR = 8000
_N = int(_SR * 0.35)


def _build_wav(path: Path) -> None:
    samples = b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / _SR)))
                       for i in range(_N))
    with path.open("wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, _SR, _SR * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", len(samples)))
        f.write(samples)


def test_modal() -> None:
    from PyQt6.QtWidgets import QApplication
    from app.ui.theme import apply_theme
    from app.ui.media_modal import MediaModal, _WaveformWidget

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)

    d = tempfile.TemporaryDirectory(prefix="modal_", ignore_cleanup_errors=True)
    wav = Path(d.name) / "demo.wav"
    _build_wav(wav)

    modal = MediaModal(wav, None)
    app.processEvents()
    assert modal.error_label.text() == "", f"error al cargar: {modal.error_label.text()!r}"
    assert modal.play_btn.isEnabled(), "play deberia habilitarse tras cargar"

    modal._toggle_play()
    app.processEvents()
    assert modal.play_btn.text() == "⏸", "play deberia estar en pausa del boton"

    modal._stop()  # boton stop: pausa + rebobina (nunca stop() de la API)
    app.processEvents()
    assert modal.slider.value() == 0 and modal.play_btn.text() == "▶"

    modal._toggle_play()
    app.processEvents()
    modal.reject()  # cierre: pausa + destruccion del player junto al dialogo
    app.processEvents()
    modal.deleteLater()
    app.processEvents()
    modal = None

    wave = _WaveformWidget(wav)
    assert len(wave.bars) == 64, "onda decorativa debe tener 64 barras"
    wave.deleteLater()

    app.processEvents()
    print("OK media_modal (audio)")
    d.cleanup()


if __name__ == "__main__":
    test_modal()
    print("SMOKE TEST FASE 4 PASSED")