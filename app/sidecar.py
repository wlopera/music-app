"""Sidecar de metadata por cancion: preserva la 'Fecha de Generacion Original'
y el nombre original del archivo antes de ser renombrado.

Vive como `.musicapp.json` dentro de cada carpeta de cancion en `carpeta_base`.
Evita que el reset del Creation Time de Windows al copiar entre volumenes
corrompa el orden cronologico. Mapea nombre de archivo -> metadatos.

Formato del sidecar (version 2):
{
  "version": 2,
  "files": {
    "Cancion_v1.mp3": {
      "original_ct": 1700000000.0,
      "original_name": "MiGrabacion_raw.mp3"
    }
  }
}
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

SIDECAR_FILENAME = ".musicapp.json"


class Sidecar:
    """Acceso read/write al archivo de metadata de una carpeta de cancion."""

    def __init__(self, folder: os.PathLike | str):
        self.folder = Path(folder)
        self.path = self.folder / SIDECAR_FILENAME

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> dict[str, Any]:
        if not self.exists():
            return {"version": 2, "files": {}}
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
                return {"version": 2, "files": {}}
            return data
        except (json.JSONDecodeError, OSError):
            return {"version": 2, "files": {}}

    def write(self, data: dict[str, Any]) -> None:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            tmp.replace(self.path)
        except OSError:
            pass

    # --- Helpers: Fecha original -------------------------------------------------
    def get_original_ct(self, filename: str) -> Optional[float]:
        data = self.read()
        entry = data.get("files", {}).get(filename)
        if isinstance(entry, dict) and entry.get("original_ct"):
            return float(entry["original_ct"])
        return None

    def set_original_ct(self, filename: str, epoch_ts: float) -> None:
        data = self.read()
        entry = data.setdefault("files", {}).setdefault(filename, {})
        entry["original_ct"] = epoch_ts
        data["version"] = 2
        self.write(data)

    # --- Helpers: Nombre original ------------------------------------------------
    def get_original_name(self, filename: str) -> Optional[str]:
        """Devuelve el nombre que tenia el archivo antes de ser renombrado a _vN."""
        data = self.read()
        entry = data.get("files", {}).get(filename)
        if isinstance(entry, dict):
            return entry.get("original_name") or None
        return None

    def set_original_name(self, filename: str, original_name: str) -> None:
        data = self.read()
        entry = data.setdefault("files", {}).setdefault(filename, {})
        entry["original_name"] = original_name
        data["version"] = 2
        self.write(data)

    # --- Helpers: escritura masiva -----------------------------------------------
    def set_many(self, mapping: dict[str, float]) -> None:
        """Compatibilidad: escribe solo original_ct (sin tocar original_name)."""
        data = self.read()
        files = data.setdefault("files", {})
        for name, ts in mapping.items():
            entry = files.setdefault(name, {})
            entry["original_ct"] = ts
        data["version"] = 2
        self.write(data)

    def set_many_full(self, mapping: dict[str, dict]) -> None:
        """Escribe original_ct y original_name juntos.

        mapping = {
            "Cancion_v1.mp3": {"original_ct": 1234.0, "original_name": "raw.mp3"},
            ...
        }
        """
        data = self.read()
        files = data.setdefault("files", {})
        for final_name, meta in mapping.items():
            entry = files.setdefault(final_name, {})
            if "original_ct" in meta:
                entry["original_ct"] = meta["original_ct"]
            if "original_name" in meta:
                entry["original_name"] = meta["original_name"]
        data["version"] = 2
        self.write(data)

    # --- Utilidades --------------------------------------------------------------
    def remove(self, filename: str) -> None:
        data = self.read()
        data.setdefault("files", {}).pop(filename, None)
        self.write(data)

    def clear_files(self) -> None:
        data = self.read()
        data["files"] = {}
        self.write(data)