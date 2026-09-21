"""Secciones colapsables (▲/▼) del layout principal."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

_HEADER_H = 46   # altura fija del encabezado cuando el panel está colapsado


class SectionPanel(QFrame):
    """Region plegable: encabezado con titulo + contador + cuerpo."""

    toggled = pyqtSignal(bool)  # True si ahora esta expandida

    def __init__(self, title: str, parent=None, initially_expanded: bool = True):
        super().__init__(parent)
        self.setObjectName("card")
        self._expanded = initially_expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 10)
        layout.setSpacing(6)

        # --- Encabezado ---
        self._header = QWidget()
        self._header.setObjectName("sectionHeader")
        self._header.setFixedHeight(_HEADER_H)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(10)

        self.arrow = QToolButton()
        self.arrow.setToolTip("Contraer / expandir")
        self.arrow.clicked.connect(self.toggle)
        header_layout.addWidget(self.arrow)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("sectionHeaderTitle")
        header_layout.addWidget(self.title_label)

        self.count_label = QLabel("")
        self.count_label.setObjectName("sectionHeaderCount")
        self.count_label.setVisible(False)
        header_layout.addWidget(self.count_label)

        header_layout.addStretch(1)
        layout.addWidget(self._header)

        # --- Cuerpo ---
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        # El cuerpo debe poder crecer verticalmente sin límite
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.body, 1)

        self._refresh_arrow()
        self._apply_expanded_state()

    # --- API ---------------------------------------------------------------------
    def set_body(self, widget: QWidget) -> None:
        self._clear_body()
        self.body_layout.addWidget(widget, 1)

    def _clear_body(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def set_count(self, text: str) -> None:
        if text:
            self.count_label.setText(text)
            self.count_label.setVisible(True)
        else:
            self.count_label.setVisible(False)

    def set_expanded(self, expanded: bool) -> None:
        if expanded != self._expanded:
            self._expanded = expanded
            self._apply_expanded_state()
            self._refresh_arrow()
            self.toggled.emit(expanded)

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    # --- Internos ----------------------------------------------------------------
    def _apply_expanded_state(self) -> None:
        """Muestra u oculta el cuerpo adaptando las restricciones para el QSplitter."""
        self.body.setVisible(self._expanded)
        if self._expanded:
            # CORREGIDO: Se limpian por completo los límites rígidos previos de altura
            self.setMaximumHeight(16_777_215)
            self.setMinimumHeight(0)
            
            # Devolvemos el control elástico total al QSplitter superior
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            # Sólo el encabezado: cálculo preciso del tamaño colapsado
            collapsed_h = _HEADER_H + 10 + 4 + 6   
            
            # CORREGIDO: En lugar de setFixedHeight (que rompe splitters), se usan límites acoplados
            self.setMinimumHeight(collapsed_h)
            self.setMaximumHeight(collapsed_h)
            
            # Informamos al layout que esta sección ahora es estricta y rígida temporalmente
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            
        # Forzar la actualización inmediata de la geometría en la interfaz de PyQt6
        self.updateGeometry()

    def _refresh_arrow(self) -> None:
        self.arrow.setText("▲" if self.is_expanded else "▼")
