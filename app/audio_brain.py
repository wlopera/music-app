"""Motor de búsqueda de canciones similares (duplicados / variantes de una composición).

Dominio puro (sin Qt), testeable headless. Las dependencias de audio
(librosa, soundfile, numpy) se cargan de forma PERZOSA vía `importlib`, de modo
que PyInstaller no las incorpora al build lean por defecto y la app funciona
aunque no estén instaladas (`availability()` devuelve falso y la UI degrada).

Cómo funciona (resumen del plan `plan/buscar_canciones.md`):
  1. `analyze_folder()`: escanea la carpeta, ignora los vídeos (sin ffmpeg en el
     MVP) y extrae por archivo una "huella" tempo-invariante: croma CQT al
     beat-sync (mediana) agregado a un vector de 12 bins normalizado, más
     `onsets_per_beat` como discriminante secundario de densidad rítmica.
  2. `build_plan()`: similitud coseno entre vectores sujeta a un umbral θ y a
     puertas baratas (proporción de duración, densidad rítmica), seguida de
     clustering por componentes conexos (equivalente a aglomerado de enlace
     único con umbral). Los grupos de ≥2 archivos se etiquetan `carpeta_N`.
  3. `execute_group_plan()`: mueve cada grupo a su carpeta con el patrón de dos
     fases (renombrado a temporal único + `fsutil.safe_move`) y registra el
     sidecar preservando `original_ct` y `original_name`, igual que el módulo
     de fusión `app/processing.py`.
"""

from __future__ import annotations

import importlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app import fsutil
from app import logs
from app.sidecar import Sidecar

logger = logs.get_logger("audio_brain")

# Extensiones analizables por librosa/libsndfile en el MVP. Los vídeos (.mp4,
# .mov, .mkv...) se listan como ignorados: necesitarían extracción ffmpeg.
AUDIO_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".wav", ".opus"})

# Umbral de tempo para chroma CQT.
_SAMPLE_RATE = 22050
# Puertas de plausibilidad entre dos perfiles.
_MAX_DURATION_RATIO = 3.0
_MAX_ONSET_DIFF = 0.35
# Duración mínima para análisis (fracciones de segundo sin contenido salen mal).
_MIN_DURATION = 0.5


# --- Datos -------------------------------------------------------------------
@dataclass
class AudioProfile:
    """Huella de un archivo de audio (o error si no se pudo analizar)."""

    path: Path
    name: str
    duration: float = 0.0
    # Vector croma 12D L2-normalizado (tempo-invariante).
    vector: Optional[list[float]] = None
    # Asaltos rítmicos por beat (None si no se detectaron beats).
    onsets_per_beat: Optional[float] = None
    beats: int = 0
    error: Optional[str] = None


@dataclass
class Analysis:
    """Resultado de escanear + extraer el universo de audio de una carpeta."""

    root_dir: Path
    profiles: list[AudioProfile] = field(default_factory=list)
    ignored: list[Path] = field(default_factory=list)   # vídeos (sin decodificador)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (nombre, razón)

    @property
    def audio_count(self) -> int:
        return len(self.profiles) + len(self.errors)


@dataclass
class GroupDraft:
    """Grupo detectado que se materializará como carpeta `carpeta_N`."""

    folder_name: str
    files: list[AudioProfile] = field(default_factory=list)
    mean_sim: float = 0.0


@dataclass
class SearchPlan:
    """Plan-then-execute: grupos a crear en la carpeta analizada."""

    root_dir: Path
    groups: list[GroupDraft] = field(default_factory=list)
    threshold: float = 0.90
    singles: int = 0                 # archivos sin pareja (se quedan en su sitio)
    errors: list[tuple[str, str]] = field(default_factory=list)
    ignored: list[Path] = field(default_factory=list)

    @property
    def files_to_move(self) -> int:
        return sum(len(g.files) for g in self.groups)


# --- Dependencias perezosas ---------------------------------------------------
_LIBS: Optional[dict[str, object]] = None
_LIBS_ERROR = ""


def availability() -> tuple[bool, str]:
    """(disponible, motivo) del motor de audio. Sin QApplication ni Qt."""
    global _LIBS, _LIBS_ERROR
    if _LIBS is not None or _LIBS_ERROR:
        return (_LIBS is not None), _LIBS_ERROR
    try:
        _LIBS = {
            "librosa": importlib.import_module("librosa"),
            "np": importlib.import_module("numpy"),
        }
        importlib.import_module("soundfile")  # decodificación wav/mp3/opus
        return True, ""
    except ImportError as exc:
        _LIBS_ERROR = (
            "Motor de audio no disponible: faltan dependencias "
            f"({exc}). Instala con: pip install -r requirements-audio.txt"
        )
        logger.warning("%s", _LIBS_ERROR)
        return False, _LIBS_ERROR


def _np() -> "object":
    return _LIBS["np"]


# --- Extracción ----------------------------------------------------------------
def extract_profile(path: Path) -> AudioProfile:
    """Huella de `path`. Nunca lanza: ante cualquier fallo devuelve `error`."""
    ok, why = availability()
    if not ok:
        return AudioProfile(path=path, name=path.name, error=why)
    libs = _LIBS
    librosa, np = libs["librosa"], libs["np"]
    try:
        y, sr = librosa.load(str(path), sr=_SAMPLE_RATE, mono=True)
        duration = float(len(y)) / sr
        if duration < _MIN_DURATION:
            return AudioProfile(path=path, name=path.name, duration=duration,
                                error=f"audio demasiado corto ({duration:.1f}s)")
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        n_beats = int(len(beats))
        if n_beats >= 2:
            chroma_sync = librosa.util.sync(chroma, beats, aggregate=np.median)
            vec = np.asarray(chroma_sync.mean(axis=1), dtype=float)
        else:
            # Sin pulso claro: croma agregado global (también invariante a tempo).
            vec = np.asarray(chroma.mean(axis=1), dtype=float)
        norm = float(np.linalg.norm(vec))
        if norm <= 1e-9:
            return AudioProfile(path=path, name=path.name, duration=duration,
                                error="sin contenido espectral aprovechable")
        onsets = librosa.onset.onset_detect(y=y, sr=sr)
        return AudioProfile(
            path=path, name=path.name, duration=duration,
            vector=(vec / norm).tolist(),
            onsets_per_beat=float(len(onsets)) / n_beats if n_beats >= 2 else None,
            beats=n_beats,
        )
    except Exception as exc:  # archivo corrupto / formato no soportado
        logger.warning("no se pudo analizar %s: %s", path.name, exc)
        return AudioProfile(path=path, name=path.name, error=str(exc))


def scan_folder(folder: Path, extensions: Optional[list[str]] = None) -> tuple[list[Path], list[Path]]:
    """(archivos de audio, archivos ignorados) de `folder` según las extensiones.

    Los ignorados son los que el plan deja fuera del MVP (vídeo sin ffmpeg).
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"La carpeta no existe: {folder}")
    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in (extensions or [])}
    audio_set = {e for e in AUDIO_EXTENSIONS if e in exts} or set(AUDIO_EXTENSIONS)
    ignored_set = {e for e in exts if e not in AUDIO_EXTENSIONS}
    return (fsutil.list_allowed_files(folder, audio_set),
            fsutil.list_allowed_files(folder, ignored_set))


def analyze_folder(folder: Path, extensions: Optional[list[str]] = None,
                   progress_cb: Optional[Callable[[int, int, str], None]] = None) -> Analysis:
    """Escanea `folder` y extrae la huella de cada archivo de audio (síncrono)."""
    ok, why = availability()
    if not ok:
        raise RuntimeError(why)
    audio_paths, ignored = scan_folder(folder, extensions)
    profiles: list[AudioProfile] = []
    errors: list[tuple[str, str]] = []
    total = len(audio_paths)
    with logs.track(logger, f"analizar '{Path(folder).name}' ({total} audio, {len(ignored)} ignorados)"):
        for i, p in enumerate(audio_paths, start=1):
            if progress_cb is not None:
                progress_cb(i, total, p.name)
            prof = extract_profile(p)
            if prof.error:
                errors.append((p.name, prof.error))
            else:
                profiles.append(prof)
        logger.info("analizar: %d perfil(es) OK, %d con error, %d ignorado(s)",
                    len(profiles), len(errors), len(ignored))
    return Analysis(root_dir=Path(folder), profiles=profiles, ignored=ignored, errors=errors)


# --- Similitud y clustering -----------------------------------------------------
def _vector(a: AudioProfile) -> "object":
    return _np().asarray(a.vector, dtype=float)


def _cosine(a: AudioProfile, b: AudioProfile) -> float:
    np = _np()
    va, vb = _vector(a), _vector(b)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(va, vb) / denom)


def _passes_gates(a: AudioProfile, b: AudioProfile) -> bool:
    """Filtros baratos para descartar parejas absurdas antes del umbral."""
    dmax, dmin = max(a.duration, b.duration), min(a.duration, b.duration) or 1e-9
    if dmax / dmin > _MAX_DURATION_RATIO:
        return False
    if a.onsets_per_beat is not None and b.onsets_per_beat is not None \
            and a.beats >= 2 and b.beats >= 2:
        diff = abs(a.onsets_per_beat - b.onsets_per_beat)
        denom = max(a.onsets_per_beat, b.onsets_per_beat) or 1e-9
        if diff / denom > _MAX_ONSET_DIFF:
            return False
    return True


def build_plan(analysis: Analysis, theta: float, prefix: str = "carpeta_") -> SearchPlan:
    """Agrupa por enlace único con umbral de coseno `theta` y numera `carpeta_N`."""
    valid = [p for p in analysis.profiles if p.error is None and p.vector]
    n = len(valid)

    # Componentes conexos: i~j si sim >= theta y pasan las puertas.
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = valid[i], valid[j]
            if not _passes_gates(a, b):
                continue
            if _cosine(a, b) >= theta:
                parent[find(i)] = find(j)
                edges += 1
    logger.info("plan: %d archivo(s), %d pareja(s) sobre umbral %.3f", n, edges, theta)

    comps: dict[int, list[AudioProfile]] = {}
    for i, p in enumerate(valid):
        comps.setdefault(find(i), []).append(p)
    grouped = [c for c in comps.values() if len(c) >= 2]
    grouped.sort(key=lambda c: (-len(c), min(p.name.lower() for p in c)))

    existing = {d.name for d in analysis.root_dir.iterdir()
                if d.is_dir() and d.name.startswith(prefix)}
    plans: list[GroupDraft] = []
    k = 1
    for comp in grouped:
        while f"{prefix}{k}" in existing:
            k += 1
        folder = f"{prefix}{k}"
        existing.add(folder)
        mean_sim = 0.0
        m = len(comp)
        pairs = 0
        for i in range(m):
            for j in range(i + 1, m):
                mean_sim += _cosine(comp[i], comp[j])
                pairs += 1
        mean_sim = mean_sim / pairs if pairs else 0.0
        plans.append(GroupDraft(folder_name=folder, files=sorted(comp, key=lambda p: p.name.lower()),
                                mean_sim=mean_sim))
        k += 1

    return SearchPlan(root_dir=analysis.root_dir, groups=plans, threshold=theta,
                      singles=n - sum(len(c) for c in grouped),
                      errors=list(analysis.errors), ignored=list(analysis.ignored))


# --- Ejecución en disco ---------------------------------------------------------
def _rename_with_retry(src: Path, dst: Path, attempts: int = 5, delay: float = 0.20) -> None:
    for i in range(attempts):
        try:
            src.rename(dst)
            return
        except PermissionError as exc:
            if i >= attempts - 1:
                logger.error("fallo definitivo al renombrar archivo bloqueado: %s", src)
                raise exc
            logger.warning("archivo bloqueado '%s'; reintento %d/%d",
                           src.name, i + 1, attempts)
            time.sleep(delay)


def execute_group_plan(plan: SearchPlan) -> dict:
    """Crea `carpeta_N` dentro de `root_dir` y mueve cada grupo transaccional.

    Mismo patrón de dos fases que `processing.execute_plan`: renombrado a temporal
    único (evita colisiones y WinError 32) + `fsutil.safe_move`. El sidecar de
    cada grupo conserva `original_ct` y `original_name`.
    """
    t0 = time.monotonic()
    root = plan.root_dir
    moved = 0
    created: list[str] = []
    for group in plan.groups:
        gdir = root / group.folder_name
        gdir.mkdir(parents=True, exist_ok=True)
        sidecar = Sidecar(gdir)
        mapping: dict[str, dict] = {}
        for prof in group.files:
            src = prof.path
            if not src.is_file():
                logger.warning("grupo %s: falta origen %s", group.folder_name, src)
                continue
            original_ct = fsutil.get_creation_time(src)
            tmp = src.parent / f".__grp_{uuid.uuid4().hex}__{src.name}"
            _rename_with_retry(src, tmp)
            fsutil.safe_move(tmp, gdir / src.name)
            fsutil.set_creation_time_windows(gdir / src.name, original_ct)
            mapping[src.name] = {"original_ct": original_ct, "original_name": src.name}
            moved += 1
            logger.info("grupo %s: %s movido", group.folder_name, src.name)
        if mapping:
            sidecar.rebuild(mapping)
        created.append(group.folder_name)
    result = {"moved": moved, "groups": created}
    logger.info("execute_group_plan: FIN %d archivo(s) en %d grupo(s) (%.2fs)",
                moved, len(created), time.monotonic() - t0)
    return result