"""Carga el tema oscuro (QSS) sobre cualquier QApplication/PyQt6."""

from pathlib import Path

_THEME_FILE = Path(__file__).with_name("theme.qss")


def apply_theme(app) -> None:
    """Aplica `theme.qss` al QApplication dado."""
    if _THEME_FILE.is_file():
        app.setStyleSheet(_THEME_FILE.read_text("utf-8"))