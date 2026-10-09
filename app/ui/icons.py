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


def music_note_icon(mode: str = "dark", size: int = 18) -> QIcon:
    """Nota musical 🎵 vectorial adaptativa al tema (celeste en oscuro, pizarra en claro)."""
    from PyQt6.QtGui import QPainterPath
    color = "#60A5FA" if mode == "dark" else "#1E293B"
    pm, p = _pixmap(size)
    c = QColor(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)

    # 1. Cabeza ovalada inclinada de la nota
    p.save()
    p.translate(size * 0.35, size * 0.72)
    p.rotate(-22)
    p.drawEllipse(QPointF(0, 0), size * 0.22, size * 0.16)
    p.restore()

    # 2. Plica vertical (tallo)
    pen = QPen(c)
    pen.setWidthF(max(1.8, size * 0.10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    stem_x = size * 0.52
    stem_top = size * 0.18
    stem_bottom = size * 0.70
    p.drawLine(QPointF(stem_x, stem_bottom), QPointF(stem_x, stem_top))

    # 3. Corchete curvado (bandera de la nota)
    path = QPainterPath()
    path.moveTo(stem_x, stem_top)
    path.cubicTo(
        QPointF(size * 0.85, stem_top + size * 0.14),
        QPointF(size * 0.78, stem_top + size * 0.38),
        QPointF(stem_x + 1, stem_top + size * 0.46)
    )
    pen.setWidthF(max(1.6, size * 0.09))
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)

    p.end()
    return QIcon(pm)
