"""Utilidades de sistema de archivos (metadata de Windows, filtros, formato de tamano)."""

import os
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
import ctypes
from ctypes import wintypes
import time

from app import logs

logger = logs.get_logger("fsutil")


def _windll() -> bool:
    return sys.platform == "win32"


# --- Tiempos --------------------------------------------------------------------
def creation_time_stats(path: os.PathLike | str) -> tuple[float, float]:
    """Retorna (creation_time, modification_time) en segundos epoch."""
    st = os.stat(path)
    return st.st_ctime, st.st_mtime


def get_creation_time(path: os.PathLike | str) -> float:
    return os.stat(path).st_ctime


def get_modification_time(path: os.PathLike | str) -> float:
    return os.stat(path).st_mtime


def format_timestamp(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "—"


# --- Tamano ---------------------------------------------------------------------
def human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            if value < 10:
                return f"{value:.2f} {unit}"
            if value < 100:
                return f"{value:.1f} {unit}"
            return f"{int(round(value))} {unit}"
        value /= 1024.0
    return f"{int(num_bytes)} B"


# --- Filtros --------------------------------------------------------------------
def safe_move(src: os.PathLike | str, dst: os.PathLike | str) -> None:
    """Mueve un archivo preservando metadata; degrada a copiar+borrar entre volumenes."""
    src = Path(src)
    dst = Path(dst)
    if src == dst:
        return
    try:
        src.replace(dst)
        logger.debug("move: %s -> %s", src, dst)
    except OSError as exc:
        logger.warning("move directo fallo (%s); degradando a copiar+borrar", exc)
        import shutil
        shutil.copy2(str(src), str(dst))
        src.unlink(missing_ok=True)
        logger.debug("move (copia+borrar): %s -> %s", src, dst)


def copy_file_responsive(src: os.PathLike | str, dst: os.PathLike | str,
                         chunk_size: int = 1 << 20, yield_cb=None) -> None:
    """Copia por bloques dejando que `yield_cb()` se ejecute entre bloques.

    Evita que copiar archivos grandes congele la interfaz (la copia ocurre en
    el hilo grafico): entre cada fragmento la app sigue procesando eventos y el
    watchdog sigue latiendo."""
    src = Path(src)
    dst = Path(dst)
    st = src.stat()
    t0 = time.monotonic()
    import shutil
    try:
        with open(src, "rb") as fin, open(dst, "wb") as fout:
            while True:
                block = fin.read(chunk_size)
                if not block:
                    break
                fout.write(block)
                if yield_cb is not None:
                    yield_cb()
        shutil.copystat(str(src), str(dst))
        os.chmod(dst, st.st_mode & 0o777)
    except BaseException as exc:
        dst.unlink(missing_ok=True)
        logger.error("copia fallida %s -> %s: %s", src, dst, exc)
        raise
    logger.debug("copia %s -> %s (%d bytes en %.2fs)",
                 src, dst, st.st_size, time.monotonic() - t0)


def is_allowed(path: os.PathLike | str, extensions: Iterable[str]) -> bool:
    p = Path(path)
    if p.is_dir():
        return False
    return p.suffix.lower() in {e.lower() for e in extensions}


def list_allowed_files(folder: os.PathLike | str, extensions: Iterable[str]) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    allowed = {e.lower() for e in extensions}
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in allowed),
                  key=lambda p: p.name.lower())


def list_subfolders(folder: os.PathLike | str) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.iterdir() if p.is_dir()),
                  key=lambda p: p.name.lower())


def list_drives() -> list[Path]:
    """Unidades de disco de Windows (p. ej. C:\\, D:\\)."""
    import string
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append(Path(drive))
    return drives


# --- Metadata de explorador -----------------------------------------------------
def file_metadata(path: os.PathLike | str, extensions: Iterable[str], sidecar_lookup=None):
    """Devuelve dict {name_ct, mod_ct, size, original_ct} o None si no aplica.

    sidecar_lookup: callable(filename)->float|None (fecha original persistida).
    """
    p = Path(path)
    if p.is_dir() or not is_allowed(p, extensions):
        return None
    ct, mt = creation_time_stats(p)
    original = ct
    if sidecar_lookup is not None:
        saved = sidecar_lookup(p.name)
        if saved:
            original = saved
    return {
        "name": p.name,
        "created": ct,
        "modified": mt,
        "original": original,
        "size": p.stat().st_size,
        "ext": p.suffix.lower(),
    }


# --- Restauracion del Creation Time en Windows ----------------------------------
def set_creation_time_windows(path: os.PathLike | str, epoch_ts: float) -> bool:
    """Escribe el Creation Time de un archivo en Windows (via SetFileTime)."""
    if not _windll():
        return False
    # 100-ns ticks desde 1601-01-01 a partir de segundos epoch
    ticks = int(epoch_ts * 10_000_000) + 116444736000000000
    lo = ticks & 0xFFFFFFFF
    hi = (ticks >> 32) & 0xFFFFFFFF
    ft = (ctypes.c_uint32 * 2)(lo, hi)

    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateFileW(
        str(Path(path)), GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, None,
        OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
    if handle == wintypes.HANDLE(-1).value or not handle:
        logger.debug("set_creation_time fallo: no se pudo abrir %s", path)
        return False
    try:
        ok = bool(kernel32.SetFileTime(handle, ctypes.byref(ft), None, None))
    finally:
        kernel32.CloseHandle(handle)
    if not ok:
        logger.warning("set_creation_time fallo (SetFileTime) en %s", path)
    return ok