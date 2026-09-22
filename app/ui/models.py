"""Modelos de datos para las tablas de archivos (columnas Explorer)."""

import os
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QColor

from app import fsutil
from app import logs

logger = logs.get_logger("models")

COL_NOMBRE = 0
COL_F_ORIGINAL = 1
COL_F_ACTUAL = 2
COL_TIPO = 3
COL_TAMANO = 4
COL_ORIGINAL = 5

# CORREGIDO: Removida la última columna de la lista de cabeceras
HEADERS = ["Nombre", "F. Original", "F. Actual", "Tipo", "Tamaño", "Original"]


class FileTableModel(QAbstractTableModel):
    """Modelo de archivos de un directorio (columnas Explorer + nombre original)."""

    def __init__(self, extensions: list[str],
                 sidecar_lookup=None,
                 sidecar_name_lookup=None,
                 directory=None):
        super().__init__()
        self.extensions = list(extensions)
        self.sidecar_lookup = sidecar_lookup          # filename -> original_ct (float)
        self.sidecar_name_lookup = sidecar_name_lookup  # filename -> original_name (str)
        self.rows: list[dict] = []
        self._directory: Optional[Path] = None
        if directory:
            self.set_directory(directory)

    # --- Datos ------------------------------------------------------------------
    def set_directory(self, directory: Optional[os.PathLike | str]) -> None:
        import time as _time
        start = _time.monotonic()
        self.beginResetModel()
        self.rows = []
        self._directory = Path(directory) if directory else None
        if self._directory and self._directory.is_dir():
            self.rows = [self._metadata(p) for p in fsutil.list_allowed_files(self._directory, self.extensions)]
        self.endResetModel()
        logger.debug("modelo cargado: %s (%d archivo(s) en %.1fms)",
                     self._directory, len(self.rows),
                     (_time.monotonic() - start) * 1000)

    def _metadata(self, path: Path) -> dict:
        md = fsutil.file_metadata(path, self.extensions, sidecar_lookup=self.sidecar_lookup)
        md["path"] = path
        return md

    @property
    def directory(self) -> Optional[Path]:
        return self._directory

    def set_extensions(self, extensions: list[str]) -> None:
        self.extensions = list(extensions)
        if self._directory:
            self.set_directory(self._directory)

    def set_sidecar_lookup(self, lookup) -> None:
        self.sidecar_lookup = lookup
        if self._directory:
            self.set_directory(self._directory)

    def set_sidecar_name_lookup(self, lookup) -> None:
        """lookup(filename) -> str | None — nombre original antes del renombrado."""
        self.sidecar_name_lookup = lookup
        if self._directory:
            self.set_directory(self._directory)

    def refresh(self) -> None:
        if self._directory:
            self.set_directory(self._directory)

    def sortKeyForColumn(self, column: int) -> Callable:
        if column == COL_F_ORIGINAL:
            return lambda r: r["original"]
        if column == COL_F_ACTUAL:
            return lambda r: r["modified"]
        if column == COL_NOMBRE:
            return lambda r: r["name"].lower()
        if column == COL_TIPO:
            return lambda r: r["ext"]
        if column == COL_ORIGINAL:
            name_of = self.sidecar_name_lookup
            if name_of:
                return lambda r: (name_of(r["name"]) or r["name"]).lower()
            return lambda r: r["name"].lower()
        return lambda r: r["size"]

    # --- QAbstractTableModel ----------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return None
        row = self.rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NOMBRE:
                return row["name"]
            if col == COL_F_ORIGINAL:
                return fsutil.format_timestamp(row["original"])
            if col == COL_F_ACTUAL:
                return fsutil.format_timestamp(row["modified"])
            if col == COL_TIPO:
                return row["ext"].lstrip(".").upper()
            if col == COL_TAMANO:
                return fsutil.human_size(row["size"])
            if col == COL_ORIGINAL:
                if self.sidecar_name_lookup:
                    return self.sidecar_name_lookup(row["name"]) or ""
                return ""
            return ""
            
        if role == Qt.ItemDataRole.ToolTipRole:
            orig = ""
            if self.sidecar_name_lookup:
                orig_val = self.sidecar_name_lookup(row["name"])
                if orig_val:
                    orig = f"\nNombre original: {orig_val}"
            return f"{row['path']}\nTamaño: {fsutil.human_size(row['size'])}{orig}"
            
        if role == Qt.ItemDataRole.UserRole:
            return row["path"]
            
        if role == Qt.ItemDataRole.ForegroundRole and col == COL_TIPO:
            return QColor("#4E5568")

        if role == Qt.ItemDataRole.ForegroundRole and col == COL_ORIGINAL:
            return QColor("#64748B")
            
        if role == Qt.ItemDataRole.TextAlignmentRole and col == COL_TAMANO:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        self.layoutAboutToBeChanged.emit()
        fn = self.sortKeyForColumn(column)
        reverse = order == Qt.SortOrder.DescendingOrder
        self.rows.sort(key=fn, reverse=reverse)
        self.layoutChanged.emit()

    def path_at(self, row: int) -> Optional[Path]:
        if 0 <= row < len(self.rows):
            return self.rows[row]["path"]
        return None

    def name_at(self, row: int) -> str:
        return self.rows[row]["name"] if 0 <= row < len(self.rows) else ""


class FilterProxy(QSortFilterProxyModel):
    """Filtra por texto sobre el modelo de archivos (por nombre)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(COL_NOMBRE)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        src = self.sourceModel()
        if src is None:
            return super().lessThan(left, right)
        col = left.column()
        lr = src.rows[left.row()]
        rr = src.rows[right.row()]
        fn = src.sortKeyForColumn(col)
        return fn(lr) < fn(rr)
