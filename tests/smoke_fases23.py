"""Smoke test de Fases 2-3: UI completa + logica de procesamiento."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _touch(path: Path, ct: float) -> None:
    path.write_bytes(b"data" * 100)
    from app import fsutil
    os.utime(path, (ct, ct))
    fsutil.set_creation_time_windows(path, ct)


def test_processing():
    from app.processing import build_plan, execute_plan
    with tempfile.TemporaryDirectory(prefix="proc_") as d:
        base = Path(d) / "base"
        stag = Path(d) / "base" / "_staging"
        base.mkdir()
        stag.mkdir()

        # copias en staging con fechas distintas (mas vieja primero)
        _touch(stag / "demo.mp3", 1_600_000_000.0)   # vieja
        _touch(stag / "demo_v2.mp4", 1_700_000_000.0)  # nueva
        _touch(stag / "demo.wav", 1_650_000_000.0)   # media

        # una version existente en el destino, cronologicamente la mas vieja
        dirl = base / "Cancion"
        dirl.mkdir()
        _touch(dirl / "Cancion_v1.mp3", 1_500_000_000.0)

        plan = build_plan("Cancion", base, stag, [".mp3", ".wav", ".mp4"])
        assert plan is not None
        names = [f.final_name for f in plan.files]
        # orden cronologico: v1=1.5e9 (existente), v2=1.6e9(mp3), v3=1.65e9(wav), v4=1.7e9(mp4)
        assert names == ["Cancion_v1.mp3", "Cancion_v2.mp3", "Cancion_v3.wav", "Cancion_v4.mp4"], names
        assert plan.staging_count == 3

        result = execute_plan(plan, [".mp3", ".wav", ".mp4"])
        assert result["moved"] == 3
        final = {p.name for p in dirl.iterdir()}
        assert final == {".version", "Cancion_v1.mp3", "Cancion_v2.mp3", "Cancion_v3.wav", "Cancion_v4.mp4"} or \
            {n for n in final if not n.startswith(".musicapp")} == {"Cancion_v1.mp3", "Cancion_v2.mp3", "Cancion_v3.wav", "Cancion_v4.mp4"}
        assert list(stag.iterdir()) == [], "staging deberia quedar vacio"

        # re-procesar sin copias nuevas: devolvia None
        plan2 = build_plan("Cancion", base, stag, [".mp3", ".wav", ".mp4"])
        assert plan2 is None

        # insertar una version mas vieja que todo -> debe ocupar v1
        _touch(stag / "OLD.mp3", 1_200_000_000.0)
        plan3 = build_plan("Cancion", base, stag, [".mp3", ".wav", ".mp4"])
        assert plan3.files[0].final_name == "Cancion_v1.mp3"
        assert plan3.files[1].final_name == "Cancion_v2.mp3"  # la anterior v1 baja a v2
        print("OK processing")


def test_ui_mainwindow():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    from app.config import ConfigManager
    from app.ui.theme import apply_theme
    from app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    with tempfile.TemporaryDirectory(prefix="ui_") as d:
        base = Path(d) / "base"
        base.mkdir()
        cfg = ConfigManager(base.parent)
        cfg.carpeta_base = str(base)
        cfg.carpeta_temporal = str(base / "_staging")
        cfg.raiz_navegacion = str(base)

        win = MainWindow(cfg)
        win.show()
        app.processEvents()

        # simular llenado y procesar (con una copia en staging)
        view = win.agrupar
        view.name_edit.setText("MiTema")
        src_dir = base / "origen"
        src_dir.mkdir()
        _touch(src_dir / "demo.mp3", 1_600_000_000.0)
        view._copy_to_staging([src_dir / "demo.mp3"])
        app.processEvents()
        assert view.staging.count() == 1
        assert view.process_btn.isEnabled(), "boton procesar deberia estar habilitado"

        view._confirm_plan = lambda plan: True  # evitar modal bloqueante en offscreen
        view._on_process()
        app.processEvents()
        ok = (base / "MiTema" / "MiTema_v1.mp3").exists()
        assert ok, "no se genero la version final tras procesar"
        assert list((base / "_staging").iterdir()) == [], "staging no limpio"
        win.close()
    print("OK ui_mainwindow")


if __name__ == "__main__":
    test_processing()
    test_ui_mainwindow()
    print("SMOKE TEST FASES 2-3 PASSED")