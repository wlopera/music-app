"""Logica de fusión y renumeración cronologica (staging -> definitiva).

Nunca toca el archivo ORIGINAL de origen: solo trabaja con las copias del
staging y con los archivos de la carpeta definitiva de la cancion.
"""

import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app import fsutil
from app import logs
from app.sidecar import Sidecar

logger = logs.get_logger("processing")


@dataclass
class Entry:
    path: Path
    name: str
    ext: str
    original_ct: float
    from_staging: bool

    @property
    def final_name(self) -> str:
        raise NotImplementedError


@dataclass
class PlannedFile:
    index: int
    final_name: str
    ext: str
    original_ct: float
    source_path: Path
    from_staging: bool
    source_name: str = ""   # nombre original antes del renombrado


@dataclass
class ProcessPlan:
    song_name: str
    target_dir: Path
    files: list[PlannedFile] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)

    @property
    def staging_count(self) -> int:
        return sum(1 for f in self.files if f.from_staging)


def _entry(path: Path, extensions: list[str], sidecar: Optional[Sidecar]) -> Optional[Entry]:
    if not path.is_file() or not fsutil.is_allowed(path, extensions):
        return None
    original = fsutil.get_creation_time(path)
    if sidecar is not None:
        saved = sidecar.get_original_ct(path.name)
        if saved:
            original = saved
    return Entry(path=path, name=path.name, ext=path.suffix.lower(),
                 original_ct=original, from_staging=False)


def collect_staging_entries(stag_dir: Path, extensions: list[str]) -> list[Entry]:
    entries = []
    for p in fsutil.list_allowed_files(stag_dir, extensions):
        e = _entry(p, extensions, sidecar=None)
        if e:
            e.from_staging = True
            entries.append(e)
    return entries


def collect_target_entries(target_dir: Path, extensions: list[str]) -> list[Entry]:
    sidecar = Sidecar(target_dir)
    return [e for e in (_entry(p, extensions, sidecar) for p in fsutil.list_allowed_files(target_dir, extensions)) if e]


def build_plan(song_name: str, base_dir: Path, stag_dir: Path, extensions: list[str]) -> Optional[ProcessPlan]:
    """Planifica el orden final de versiones (sin ejecutar nada)."""
    song_name = song_name.strip()
    if not song_name:
        return None
    target_dir = (Path(base_dir) / song_name)
    if not Path(base_dir).is_dir():
        raise FileNotFoundError(f"La carpeta base no existe: {base_dir}")

    staging_entries = collect_staging_entries(stag_dir, extensions)
    target_entries = collect_target_entries(target_dir, extensions)
    logger.info("build_plan '%s': %d del staging, %d existentes en %s",
                song_name, len(staging_entries), len(target_entries), target_dir)

    if not staging_entries:
        return None  # no hay nada nuevo que procesar

    merged = target_entries + staging_entries
    merged.sort(key=lambda e: (e.original_ct, e.name.lower()))

    plan = ProcessPlan(song_name=song_name, target_dir=target_dir)
    for i, e in enumerate(merged, start=1):
        final = f"{song_name}_v{i}{e.ext}"
        plan.files.append(PlannedFile(
            index=i, final_name=final, ext=e.ext, original_ct=e.original_ct,
            source_path=e.path, from_staging=e.from_staging,
            source_name=e.name))   # preservar el nombre antes del renombrado
    return plan


def execute_plan(plan: ProcessPlan, extensions: list[str]) -> dict:
    """Ejecuta la fusion: mueve/renombra por fecha original y escribe el sidecar."""
    target_dir = plan.target_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    # Fase 1: liberar todos los nombres hacia temporales unicos en su mismo dir
    pending_moves: list[tuple[Path, str]] = []   # (tmp_path, final_name)
    staging_tmps: list[tuple[Path, Path, str]] = []  # (tmp_path in staging, staging_dir, final_name)

    moved = 0
    logger.info("execute_plan: %d archivo(s) hacia %s", len(plan.files), target_dir)
    renamed_existing = 0
    for item in plan.files:
        src = item.source_path
        tmp = src.parent / f".__mv_{uuid.uuid4().hex}__{src.name}"
        src.rename(tmp)
        logger.debug("  temp-rename: %s -> %s", src.name, tmp.name)
        if item.from_staging:
            staging_tmps.append((tmp, src.parent, item.final_name))
        else:
            pending_moves.append((tmp, item.final_name))
            renamed_existing += 1

    # Fase 2: mover temporales del staging hacia el destino con su nombre final
    for tmp, src_dir, final_name in staging_tmps:
        dst = target_dir / final_name
        fsutil.safe_move(tmp, dst)
        moved += 1
        logger.info("  staging -> definitivo: %s (%s)", final_name, tmp.name)

    # Fase 3: renombrar temporales del destino a su nombre final
    for tmp, final_name in pending_moves:
        dst = target_dir / final_name
        tmp.replace(dst)
        logger.info("  renombrado existente: %s -> %s", tmp.name, final_name)

    # Fase 4: restaurar fechas originales + escribir sidecar (ct + nombre original)
    sidecar = Sidecar(target_dir)
    mapping: dict[str, dict] = {}
    for item in plan.files:
        dst = target_dir / item.final_name
        if not dst.exists():
            continue
        fsutil.set_creation_time_windows(dst, item.original_ct)
        meta: dict = {"original_ct": item.original_ct}
        if item.source_name and item.source_name != item.final_name:
            meta["original_name"] = item.source_name
        mapping[item.final_name] = meta
    if mapping:
        sidecar.set_many_full(mapping)
        logger.info("sidecar actualizado con %d entrada(s) (ct + nombre original)", len(mapping))

    return {"moved": moved, "target_dir": str(target_dir), "files": len(plan.files)}