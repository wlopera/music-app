"""Test del motor de búsqueda de canciones (app/audio_brain.py).

Cobertura principal:
  * Invariante de tempo: la misma melodía a 90/120/150 BPM debe agruparse junta.
  * Discriminación: una melodía distinta a la misma velocidad NO entra al grupo.
  * Tolerancia a corruptos: un archivo dañado se salta (errors) sin abortar.
  * Vídeos: sin ffmpeg en el MVP, se ignoran (no se analizan).
  * Ejecución en disco: execute_group_plan crea carpeta_N, mueve los archivos
    y deja el sidecar con original_ct / original_name.

Sin dependencias de audio instaladas el test se omite (SKIP), no falla.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SR = 22050
BASE = 220.0
MEL_A = [0, 4, 7, 5, 4, 2, 0, 4]
MEL_B = [11, 10, 8, 6, 7, 5, 3, 2]


def _render(steps, bpm, seconds=8.0) -> "np.ndarray":
    import numpy as np
    beat = 60.0 / bpm
    eighth = beat / 2.0
    note_len = eighth * 0.85
    total = int(seconds * SR)
    y = np.zeros(total)
    n_notes = int(seconds / eighth)
    for k in range(n_notes):
        step = steps[k % len(steps)]
        f = BASE * (2.0 ** (step / 12.0))
        i0 = int(k * eighth * SR)
        n = int(note_len * SR)
        if i0 + n > total:
            n = total - i0
        t = np.arange(n) / SR
        y[i0:i0 + n] += 0.35 * np.exp(-t * 6.0) * np.sin(2 * np.pi * f * t)
    return y


def _build_corpus(folder: Path) -> None:
    from app import audio_brain
    import soundfile as sf
    for bpm, tag in ((90, "90"), (120, "120"), (150, "150")):
        sf.write(str(folder / f"melodiaA_{tag}bpm.wav"),
                 _render(MEL_A, bpm), SR, subtype="PCM_16")
    sf.write(str(folder / "otraCancion_120bpm.wav"), _render(MEL_B, 120),
             SR, subtype="PCM_16")
    (folder / "danado.mp3").write_bytes(b"ID3" + b"\x00" * 4000)
    (folder / "video_promo.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)


def test_plan() -> None:
    from app import audio_brain
    with tempfile.TemporaryDirectory(prefix="brain_") as d:
        folder = Path(d) / "universo"
        folder.mkdir()
        _build_corpus(folder)

        analysis = audio_brain.analyze_folder(
            folder, [".wav", ".mp3", ".mp4", ".opus"],
            progress_cb=lambda done, total, name: None)
        # 3 variantes de A + 1 melodía B analizables; 1 corrupto; 1 vídeo ignorado
        assert len(analysis.profiles) == 4, analysis.profiles
        assert [name for name, _ in analysis.errors] == ["danado.mp3"]
        assert [p.name for p in analysis.ignored] == ["video_promo.mp4"]

        plan = audio_brain.build_plan(analysis, theta=0.90)
        assert len(plan.groups) == 1, [g.folder_name for g in plan.groups]
        group = plan.groups[0]
        names = {f.name for f in group.files}
        assert names == {"melodiaA_90bpm.wav", "melodiaA_120bpm.wav",
                         "melodiaA_150bpm.wav"}, names
        assert "otraCancion_120bpm.wav" not in names
        assert plan.singles == 1
        assert group.mean_sim > 0.9, group.mean_sim

        # Ejecución en disco: carpeta_N creada, archivos movidos, sidecar ok.
        result = audio_brain.execute_group_plan(plan)
        assert result["moved"] == 3, result
        assert result["groups"] == ["carpeta_1"], result
        gdir = folder / "carpeta_1"
        assert gdir.is_dir()
        assert sorted(p.name for p in gdir.iterdir()
                      if p.is_file() and p.name != ".musicapp.json") == sorted(names)
        from app import audio_brain as ab
        from app.sidecar import Sidecar
        sidecar = Sidecar(gdir).read()
        assert len(sidecar.get("files", {})) == 3
        entry = sidecar["files"]["melodiaA_90bpm.wav"]
        assert entry.get("original_name") == "melodiaA_90bpm.wav"
        assert entry.get("original_ct", 0) > 0


def main() -> int:
    from app import audio_brain
    ok, why = audio_brain.availability()
    if not ok:
        print(f"SKIP audio_brain: {why}")
        return 0
    test_plan()
    print("OK audio_brain (tempo-invariante, corruptos, videos y ejecución en disco)")
    return 0


if __name__ == "__main__":
    sys.exit(main())