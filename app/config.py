"""Gestion del archivo de configuracion `config.json` (portable, junto al ejecutable)."""

import json
from pathlib import Path
from typing import Any, Optional

from app import logs
from app.version import normalize as _normalize_version

logger = logs.get_logger("config")

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "",
    "tema": "oscuro",
    "carpeta_base": "",
    "carpeta_temporal": "",
    "extensiones_permitidas": [".mp3", ".wav", ".opus", ".flac", ".ogg", ".aiff", ".aif"],
    "raiz_navegacion": "",
}

_STAGING_SUBFOLDER = "_staging"


class ConfigManager:
    """Lee, crea y guarda `config.json`. Subida auto-generada si no existe."""

    def __init__(self, base_dir: Path, filename: str = "config.json"):
        self.base_dir = Path(base_dir)
        self.path = self.base_dir / filename
        self.data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self.data = {**DEFAULT_CONFIG, **{k: v for k, v in raw.items() if k in DEFAULT_CONFIG}}
                self.data["version"] = _normalize_version(self.data.get("version"))
                logger.debug("config cargada de %s (%d clave(s))", self.path, len(self.data))
                return
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("config %s corrupta/inaccesible (%s); usando valores por defecto", self.path, exc)
                self.data = dict(DEFAULT_CONFIG)
        else:
            self.data = dict(DEFAULT_CONFIG)
        self.data["version"] = _normalize_version(self.data.get("version"))
        self.save()
        logger.info("config auto-generada en %s", self.path)

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=4, ensure_ascii=False), encoding="utf-8")
        logger.debug("config guardada en %s: %s", self.path, {k: v for k, v in self.data.items()})

    # --- Propiedades esenciales -------------------------------------------------
    @property
    def version(self) -> str:
        """Version `1.ddmmyy-nro` vigente (normalizada; auto-correcta si esta corrupta)."""
        return _normalize_version(self.data.get("version"))

    @version.setter
    def version(self, value: str) -> None:
        self.data["version"] = _normalize_version(value)
        self.save()

    @property
    def tema(self) -> str:
        """'claro' | 'oscuro' (por defecto 'oscuro'; otros valores caen a 'claro')."""
        v = str(self.data.get("tema", "oscuro")).strip().lower()
        return "oscuro" if v.startswith("osc") or v == "dark" else "claro"

    @tema.setter
    def tema(self, value: str) -> None:
        self.data["tema"] = "oscuro" if str(value).lower().startswith(("osc", "dark")) else "claro"
        self.save()

    @property
    def carpeta_base(self) -> Optional[str]:
        v = self.data.get("carpeta_base", "")
        return v if v else None

    @carpeta_base.setter
    def carpeta_base(self, value: str) -> None:
        self.data["carpeta_base"] = value or ""
        self.save()

    @property
    def carpeta_temporal(self) -> Optional[str]:
        """Directorio puente; por defecto vive dentro de carpeta_base como `_staging`."""
        v = self.data.get("carpeta_temporal", "")
        if v:
            return v
        if self.carpeta_base:
            return str(Path(self.carpeta_base) / _STAGING_SUBFOLDER)
        return None

    @carpeta_temporal.setter
    def carpeta_temporal(self, value: str) -> None:
        self.data["carpeta_temporal"] = value or ""
        self.save()

    @property
    def raiz_navegacion(self) -> Optional[str]:
        v = self.data.get("raiz_navegacion", "")
        return v if v else None

    @raiz_navegacion.setter
    def raiz_navegacion(self, value: str) -> None:
        self.data["raiz_navegacion"] = value or ""
        self.save()

    @property
    def extensiones_permitidas(self) -> list[str]:
        exts = self.data.get("extensiones_permitidas", [])
        normalized = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in exts]
        return normalized or list(DEFAULT_CONFIG["extensiones_permitidas"])

    @extensiones_permitidas.setter
    def extensiones_permitidas(self, values: list[str]) -> None:
        clean: list[str] = []
        for e in values:
            e = (e or "").strip().lower()
            if e and not e.startswith("."):
                e = f".{e}"
            if e and e not in clean:
                clean.append(e)
        self.data["extensiones_permitidas"] = clean
        self.save()

    # --- Utilidades -------------------------------------------------------------
    def detalles(self) -> dict[str, Any]:
        return {
            "carpeta_base": self.carpeta_base or "",
            "carpeta_temporal": self.carpeta_temporal or "",
            "carpeta_temporal_configurada": bool(self.data.get("carpeta_temporal")),
            "raiz_navegacion": self.raiz_navegacion or "",
            "extensiones_permitidas": self.extensiones_permitidas,
        }