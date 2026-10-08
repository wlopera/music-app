"""Iconos vectoriales dibujados con QPainter (luna / sol) — sin assets externos."""

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def _pixmap(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pm, p


def moon_icon(size: int = 18, color: str = "#2563EB") -> QIcon:
    """Crescente de luna: circulo completo menos un circulo desplazado."""
    pm, p = _pixmap(size)
    c = QColor(color)
    r = size * 0.40
    center = QPointF(size / 2, size / 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawEllipse(center, r, r)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    p.drawEllipse(QPointF(size / 2 + r * 0.55, size / 2 - r * 0.45), r * 0.95, r * 0.95)
    p.end()
    return QIcon(pm)


def sun_icon(size: int = 18, color: str = "#F59E0B") -> QIcon:
    """Sol: nucleo + 8 rayos."""
    pm, p = _pixmap(size)
    c = QColor(color)
    cx = cy = size / 2
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(cx, cy), size * 0.21, size * 0.21)
    pen = QPen(c)
    pen.setWidthF(max(1.5, size * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    inner, outer = size * 0.32, size * 0.46
    for i in range(8):
        a = math.radians(i * 45)
        p.drawLine(QPointF(cx + math.cos(a) * inner, cy + math.sin(a) * inner),
                   QPointF(cx + math.cos(a) * outer, cy + math.sin(a) * outer))
    p.end()
    return QIcon(pm)


def theme_icon(mode: str, size: int = 18) -> QIcon:
    """Icono del modo al que SE PUEDE cambiar (luna -> oscuro, sol -> claro)."""
    if mode == "dark":
        return sun_icon(size, "#FBBF24")
    return moon_icon(size, "#2563EB")
