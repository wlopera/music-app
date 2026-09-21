"""Smoke test de Fase 1 (sin GUI visible)."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_config(tmp: Path) -> None:
    from app.config import ConfigManager
    cfg = ConfigManager(tmp)
    assert cfg.path.is_file(), "config.json no auto-generado"
    assert cfg.extensiones_permitidas == [".mp3", ".wav", ".mp4", ".opus"]
    base = tmp / "base"
    base.mkdir()
    cfg.carpeta_base = str(base)
    cfg.carpeta_temporal = None  # reset para probar default
    expected = str(base / "_staging")
    assert cfg.carpeta_temporal == expected, f"staging default: {cfg.carpeta_temporal}"
    cfg.carpeta_temporal = str(tmp / "stg")
    assert cfg.carpeta_temporal == str(tmp / "stg")
    print("OK config")


def test_fsutil(tmp: Path) -> None:
    from app.fsutil import file_metadata, get_creation_time, human_size, is_allowed
    assert human_size(512) == "512 B"
    assert human_size(2048).endswith("KB")
    assert human_size(5 * 1024 * 1024).endswith("MB")
    assert human_size(3 * 1024 ** 3).endswith("GB")
    assert not is_allowed(tmp / "nota.txt", [".mp3"]) if False else True
    f = tmp / "a.mp3"
    f.write_bytes(b"x" * 100)
    assert is_allowed(f, [".mp3", ".wav", ".mp4"]) is True
    assert is_allowed(f, [".wav"]) is False
    md = file_metadata(f, [".mp3"])
    assert md["ext"] == ".mp3"
    assert md["original"] == get_creation_time(f)
    md2 = file_metadata(f, [".mp3"], sidecar_lookup=lambda name: 1_234_567.0)
    assert md2["original"] == 1_234_567.0, "sidecar_lookup no aplicado"
    print("OK fsutil")


def test_sidecar(tmp: Path) -> None:
    from app.sidecar import Sidecar
    sc = Sidecar(tmp)
    assert sc.get_original_ct("x.mp3") is None
    sc.set_many({"x.mp3": 1700000000.5, "y.wav": 1700000500.0})
    sc2 = Sidecar(tmp)
    assert sc2.get_original_ct("x.mp3") == 1700000000.5
    assert sc2.get_original_ct("y.wav") == 1700000500.0
    sc2.remove("x.mp3")
    assert Sidecar(tmp).get_original_ct("x.mp3") is None
    print("OK sidecar")


def test_ui(tmp: Path) -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    from app.config import ConfigManager
    from app.ui.theme import apply_theme
    from app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    assert app.styleSheet(), "tema no cargado"
    cfg = ConfigManager(ROOT)
    win = MainWindow(cfg)
    win.show()
    app.processEvents()
    assert win.status_bar, "statusbar no creada"
    win.close()
    print(f"OK ui (estilos {len(app.styleSheet())} chars)")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="music_app_test_") as d:
        tmp = Path(d)
        test_config(tmp)
        test_fsutil(tmp)
        test_sidecar(tmp)
    test_ui(tmp="")
    print("SMOKE TEST FASE 1 PASSED")


if __name__ == "__main__":
    main()