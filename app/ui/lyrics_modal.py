"""Ventana modal minimalista para visualizar y copiar la letra de una canción."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                             QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)


class LyricsModal(QDialog):
    """Modal elegante para ver la letra nativa de una composición o aviso de ausencia."""

    def __init__(self, song_name: str, lyrics: Optional[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Letra · {song_name}")
        self.resize(580, 520)
        self.setMinimumSize(420, 360)

        # Habilitar botones de ventana estándar
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        # Cabecera con título
        head_row = QHBoxLayout()
        icon_lbl = QLabel("📝")
        icon_lbl.setStyleSheet("font-size: 16pt;")
        head_row.addWidget(icon_lbl)

        title_lbl = QLabel(song_name)
        title_lbl.setObjectName("sectionHeaderTitle")
        title_lbl.setStyleSheet("font-size: 11pt; font-weight: bold;")
        head_row.addWidget(title_lbl, 1)
        layout.addLayout(head_row)

        if lyrics and lyrics.strip():
            self.text_edit = QPlainTextEdit()
            self.text_edit.setObjectName("logViewer")
            self.text_edit.setReadOnly(True)
            font = QFont("Segoe UI", 10)
            self.text_edit.setFont(font)
            self.text_edit.setPlainText(lyrics.strip())
            layout.addWidget(self.text_edit, 1)

            # Botonera inferior
            btn_row = QHBoxLayout()
            self.copy_btn = QPushButton("📋 Copiar Letra")
            self.copy_btn.setObjectName("btnPrimary")
            self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.copy_btn.clicked.connect(self._copy_lyrics)
            btn_row.addWidget(self.copy_btn)

            btn_row.addStretch(1)

            close_btn = QPushButton("Cerrar")
            close_btn.setObjectName("btnSecondary")
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.clicked.connect(self.accept)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)
        else:
            # Estado sin letra
            info_card = QWidget()
            info_card.setObjectName("card")
            card_lay = QVBoxLayout(info_card)
            card_lay.setContentsMargins(20, 24, 20, 24)
            card_lay.setSpacing(10)

            msg1 = QLabel("ℹ️ Esta canción no tiene letra registrada.")
            msg1.setObjectName("sectionHeaderTitle")
            msg1.setStyleSheet("font-size: 11pt; font-weight: 600; color: #F59E0B;")
            card_lay.addWidget(msg1)

            hint = QLabel(
                "No se encontró texto incrustado en los metadatos ID3 (frame USLT) "
                "ni un archivo de texto acompañante (.txt o .lrc) con el mismo nombre en la carpeta.\n\n"
                "💡 Para registrar la letra de forma inmediata:\n"
                "Crea un archivo de texto junto a la canción con su mismo nombre, por ejemplo:\n"
                f"   • {song_name}.txt\n"
                "y el sistema la reconocerá automáticamente sin necesidad de reconfigurar nada."
            )
            hint.setObjectName("mutedLabel")
            hint.setWordWrap(True)
            hint.setStyleSheet("line-height: 1.4;")
            card_lay.addWidget(hint)
            layout.addWidget(info_card, 1)

            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            close_btn = QPushButton("Cerrar")
            close_btn.setObjectName("btnSecondary")
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.clicked.connect(self.accept)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

    def _copy_lyrics(self) -> None:
        if hasattr(self, "text_edit"):
            text = self.text_edit.toPlainText()
            clipboard = QApplication.clipboard()
            if clipboard and text:
                clipboard.setText(text)
                self.copy_btn.setText("✓ Copiado")
