"""Control de versiones: `1.ddmmyy-nro` persistido en `config.json`.

Formato: 1.<dd><mm><yy>-<nro>
  dd = dia, mm = mes, yy = dos digitos del anio, nro = consecutivo del dia.

Uso:
    from app.version import current, bump
    current(config)   -> "1.081026-1"
    bump(config)      -> "1.081026-2"  (misma fecha) o "1.081027-1" (nuevo dia)

CLI (desde la raiz del proyecto):
    python -m app.version        # muestra la version actual
    python -m app.version bump   # incrementa y guarda en config.json
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from app import __version__ as _PKG_VERSION

_VERSION_RE = re.compile(r"^1\.(\d{6})-(\d+)$")
FALLBACK = _PKG_VERSION


def today_stamp(day: Optional[date] = None) -> str:
    """`ddmmyy` del dia dado (hoy por defecto)."""
    d = day or date.today()
    return d.strftime("%d%m%y")


def make(day: Optional[date] = None, nro: int = 1) -> str:
    """Compone `1.ddmmyy-nro`."""
    return f"1.{today_stamp(day)}-{int(nro)}"


def bump(current_version: str, day: Optional[date] = None) -> str:
    """Siguiente version: mismo dia -> nro+1; otro dia -> nro=1."""
    m = _VERSION_RE.match((current_version or "").strip())
    if not m:
        return make(day, 1)
    stamp, nro = m.group(1), int(m.group(2))
    if stamp == today_stamp(day):
        return f"1.{stamp}-{nro + 1}"
    return make(day, 1)


def normalize(raw: object) -> str:
    """Devuelve una version valida a partir de cualquier valor."""
    s = str(raw or "").strip()
    return s if _VERSION_RE.match(s) else FALLBACK


def _config_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    return root / "config.json"


def current(config=None) -> str:
    """Version vigente: la de `config` (ConfigManager) o la de `config.json`."""
    if config is not None:
        return normalize(getattr(config, "version", None))
    import json
    path = _config_path()
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return FALLBACK
    return normalize(data.get("version"))


def bump_and_save(config=None) -> str:
    """Incrementa la version y la persiste en `config.json`."""
    if config is not None:
        new = bump(normalize(getattr(config, "version", None)))
        config.version = new  # property con guardado automatico
        return new
    import json
    path = _config_path()
    data = {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        pass
    data["version"] = bump(normalize(data.get("version")))
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), "utf-8")
    return data["version"]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "bump":
        print(bump_and_save())
    else:
        print(current())
