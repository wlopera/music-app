"""Panel colapsable de logs para visualizar trazas y errores en tiempo real."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                             QPlainTextEdit, QPushButton, QToolButton,
                             QVBoxLayout, QWidget)

from app import logs


class _LogBridge(QObject):
    """Puente seguro entre hilos: emite señales Qt hacia el hilo GUI."""

    new_record = pyqtSignal(str, int)  # (mensaje_formateado, levelno)


class _QtLogHandler(logging.Handler):
    """Handler de logging que redirige los registros al puente Qt."""

    def __init__(self, bridge: _LogBridge):
        super().__init__()
        self.bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.bridge.new_record.emit(msg, record.levelno)
        except Exception:
            self.handleError(record)


class LogPanel(QWidget):
    """Barra inferior con visor de trazas colapsable, contador de errores y botón limpiar."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("logPanel")

        self._is_expanded = False
        self._error_count = 0
        self._warning_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Cabecera / Barra de control -----------------------------------
        self.header_bar = QFrame()
        self.header_bar.setObjectName("logHeader")
        self.header_bar.setFixedHeight(26)

        head_lay = QHBoxLayout(self.header_bar)
        head_lay.setContentsMargins(10, 0, 10, 0)
        head_lay.setSpacing(8)

        # Botón conmutador con icono > / v
        self.toggle_btn = QToolButton()
        self.toggle_btn.setObjectName("logToggleBtn")
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setText(">  Registros")
        self.toggle_btn.setToolTip("Mostrar / Ocultar consola de registros")
        self.toggle_btn.clicked.connect(self.toggle_collapsed)
        head_lay.addWidget(self.toggle_btn)

        # Badge indicador de errores / avisos
        self.badge_label = QLabel("")
        self.badge_label.setObjectName("logBadge")
        head_lay.addWidget(self.badge_label)

        head_lay.addStretch(1)

        # Botón Copiar
        self.copy_btn = QPushButton("Copiar")
        self.copy_btn.setObjectName("logActionBtn")
        self.copy_btn.setToolTip("Copiar registros al portapapeles")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_logs)
        head_lay.addWidget(self.copy_btn)

        # Botón Limpiar
        self.clear_btn = QPushButton("Limpiar")
        self.clear_btn.setObjectName("logActionBtn")
        self.clear_btn.setToolTip("Limpiar registros de la pantalla")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_logs)
        head_lay.addWidget(self.clear_btn)

        layout.addWidget(self.header_bar)

        # --- Contenedor del visor (área deslizable) ------------------------
        self.body_container = QWidget()
        self.body_container.setObjectName("logBodyContainer")
        self.body_container.setFixedHeight(135)
        self.body_container.setVisible(False)

        body_lay = QVBoxLayout(self.body_container)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        self.viewer = QPlainTextEdit()
        self.viewer.setObjectName("logViewer")
        self.viewer.setReadOnly(True)
        self.viewer.setMaximumBlockCount(3000)
        # Fuente monoespaciada para legibilidad de trazas
        font = QFont("Consolas", 8)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.viewer.setFont(font)
        body_lay.addWidget(self.viewer)

        layout.addWidget(self.body_container)

        # --- Conexión con el sistema de logs --------------------------------
        self.bridge = _LogBridge()
        self.bridge.new_record.connect(self._on_log_record)

        self._handler = _QtLogHandler(self.bridge)
        formatter = logging.Formatter(
            "%(asctime)s.%(msecs)03d %(levelname)-7s [%(name)s] %(message)s",
            datefmt="%H:%M:%S")
        self._handler.setFormatter(formatter)
        logging.getLogger("musicapp").addHandler(self._handler)

        self._preload_recent_logs()
        self._update_badge()

    def toggle_collapsed(self) -> None:
        self.set_expanded(not self._is_expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._is_expanded = expanded
        self.body_container.setVisible(expanded)
        icon = "v" if expanded else ">"
        self.toggle_btn.setText(f"{icon}  Registros")
        if expanded:
            self._scroll_to_bottom()

    def clear_logs(self) -> None:
        self.viewer.clear()
        self._error_count = 0
        self._warning_count = 0
        self._update_badge()

    def _copy_logs(self) -> None:
        text = self.viewer.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)

    def _update_badge(self) -> None:
        if self._error_count > 0 and self._warning_count > 0:
            self.badge_label.setText(
                f"❌ {self._error_count} error(es) · ⚠️ {self._warning_count} aviso(s)")
            self.badge_label.setStyleSheet("color: #F87171; font-weight: 600; font-size: 8.5pt;")
        elif self._error_count > 0:
            self.badge_label.setText(f"❌ {self._error_count} error(es)")
            self.badge_label.setStyleSheet("color: #F87171; font-weight: 600; font-size: 8.5pt;")
        elif self._warning_count > 0:
            self.badge_label.setText(f"⚠️ {self._warning_count} aviso(s)")
            self.badge_label.setStyleSheet("color: #FBBF24; font-weight: 600; font-size: 8.5pt;")
        else:
            self.badge_label.setText("✓ Sin errores")
            self.badge_label.setStyleSheet("color: #10B981; font-size: 8.5pt;")

    def _on_log_record(self, msg: str, level: int) -> None:
        if level >= logging.ERROR:
            self._error_count += 1
            self._update_badge()
        elif level >= logging.WARNING:
            self._warning_count += 1
            self._update_badge()

        self.viewer.appendPlainText(msg)
        if self._is_expanded:
            self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        cursor = self.viewer.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.viewer.setTextCursor(cursor)

    def _preload_recent_logs(self) -> None:
        """Carga las últimas líneas del archivo de log si ya existe en disco."""
        try:
            # Buscar musicapp.log junto a la app o en dist
            candidates = [
                Path("musicapp.log"),
                Path("dist/Music-App/musicapp.log"),
            ]
            for log_file in candidates:
                if log_file.is_file():
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    tail = lines[-40:] if len(lines) > 40 else lines
                    for line in tail:
                        line_clean = line.rstrip("\r\n")
                        if "ERROR" in line_clean or "CRITICAL" in line_clean:
                            self._error_count += 1
                        elif "WARNING" in line_clean:
                            self._warning_count += 1
                        self.viewer.appendPlainText(line_clean)
                    break
        except Exception:
            pass
