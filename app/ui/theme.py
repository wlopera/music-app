"""Carga del tema QSS (claro/oscuro) sobre cualquier QApplication/PyQt6."""

from pathlib import Path

_DIR = Path(__file__).resolve().parent
_FILES = {
    "light": _DIR / "theme.qss",
    "dark": _DIR / "theme_dark.qss",
}

_mode = "light"


def current_mode() -> str:
    """Modo de tema activo ('light' | 'dark')."""
    return _mode


def apply_theme(app, mode: str = "light") -> str:
    """Aplica `theme.qss` o `theme_dark.qss` al QApplication dado y devuelve el modo."""
    global _mode
    _mode = "dark" if str(mode).lower().startswith("d") else "light"
    path = _FILES[_mode]
    if path.is_file():
        app.setStyleSheet(path.read_text("utf-8"))
    return _mode


def toggle_theme(app) -> str:
    """Alterna entre claro y oscuro; devuelve el modo resultante."""
    return apply_theme(app, "light" if _mode == "dark" else "dark")
