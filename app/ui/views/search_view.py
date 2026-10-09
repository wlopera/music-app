"""Vista «Buscar Canciones»: motor de detección de canciones similares (fase 2).

Flujo plan-then-execute (mismo espíritu que Agrupar Temas):
  1. La carpeta a analizar (universo) se analiza con `SearchAnalyzer` en un hilo de
     fondo (threading plano) mientras la UI muestra progreso; nunca bloquea la
     interfaz.
  2. `build_plan()` agrupa por similitud y etiqueta los grupos `carpeta_N`;
     se muestra una VISTA PREVIA antes de tocar disco.
  3. «EJECUTAR GRUPOS» crea las carpetas y mueve los archivos reutilizando el
     patrón de dos fases + sidecar (original_ct / original_name).
Si faltan las dependencias de audio (librosa), la vista degrada con un aviso.
"""

import time
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QProgressBar, QPushButton,
                             QScrollArea, QSlider, QToolButton, QVBoxLayout, QWidget)

from app import audio_brain
from app import logs
from app.config import ConfigManager
from app.ui.search_worker import SearchAnalyzer

logger = logs.get_logger("search_view")

_THETA_MIN = 0.975   # Flexible (variaciones de ritmo / tempo)
_THETA_MAX = 0.995   # Estricto (duplicados exactos)
_MAX_GROUPS_SHOWN = 50
_MAX_FILES_LIMIT = 100
_MAX_FILE_SIZE_MB = 150
_MAX_FILE_SIZE_BYTES = 150 * 1024 * 1024


def _fmt_dur(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class _SongRowWidget(QFrame):
    """Fila interactiva de canción con audición directa, visor de letra y doble clic."""

    def __init__(self, profile: audio_brain.AudioProfile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Doble clic para reproducir canción")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(6)

        lbl = QLabel(f"🎵  {profile.name}  ({_fmt_dur(profile.duration)})")
        lbl.setObjectName("mutedLabel")
        lay.addWidget(lbl, 1)

        # Botón Play
        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("logActionBtn")
        self.play_btn.setToolTip("Reproducir canción")
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self._play_song)
        lay.addWidget(self.play_btn)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._play_song()
        super().mouseDoubleClickEvent(event)

    def _play_song(self) -> None:
        from app.ui.media_modal import MediaModal
        modal = MediaModal(self.profile.path, self.window())
        modal.show()


class SearchView(QWidget):
    """Panel derecho: buscador de canciones iguales dentro de un universo."""

    statusMessage = pyqtSignal(str, int)  # texto, timeout ms (0 = permanente)

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.last_status = ""
        self._plan = None
        self._last_analysis = None
        self._busy = False
        self._engine_ok, self._engine_why = audio_brain.availability()
        # Analiza en un hilo de fondo (threading plano) y entrega señales al hilo
        # GUI; ver app/ui/search_worker.py.
        self._analyzer = SearchAnalyzer(self)
        self._analyzer.progress.connect(self._on_progress)
        self._analyzer.analyzed.connect(self._on_analyzed)
        self._analyzer.failed.connect(self._on_failed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 8)
        lay.setSpacing(10)

        # --- Título + estado del motor ------------------------------------
        title_row = QHBoxLayout()
        icon = QLabel("🔍")
        icon.setStyleSheet("font-size: 16pt;")
        title_row.addWidget(icon)
        title = QLabel("BUSCAR CANCIONES SIMILARES")
        title.setObjectName("topbarTitle")
        title.setStyleSheet("font-size: 14pt; letter-spacing: 2px;")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.engine_badge = QLabel(
            "Motor de audio disponible" if self._engine_ok else "Motor no disponible")
        self.engine_badge.setObjectName("welcomeHint")
        self.engine_badge.setToolTip(
            "" if self._engine_ok
            else "Instala el motor opcional:  pip install -r requirements-audio.txt")
        title_row.addWidget(self.engine_badge)
        lay.addLayout(title_row)

        # --- Panel: parámetros del análisis --------------------------------
        cfg = QFrame()
        cfg.setObjectName("card")
        cfg_lay = QVBoxLayout(cfg)
        cfg_lay.setContentsMargins(12, 10, 12, 12)
        cfg_lay.setSpacing(10)

        cfg_title = QLabel("UNIVERSO DE AUDIO")
        cfg_title.setObjectName("sectionHeaderTitle")
        cfg_lay.addWidget(cfg_title)

        # Ruta a analizar
        path_row = QHBoxLayout()
        path_label = QLabel("Ruta a analizar:")
        path_row.addWidget(path_label)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Carpeta con las canciones a revisar…")
        self.path_edit.textChanged.connect(self._on_path_changed)
        path_row.addWidget(self.path_edit, 1)
        self.browse_btn = QToolButton()
        self.browse_btn.setText("…")
        self.browse_btn.setToolTip("Elegir carpeta…")
        self.browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.browse_btn)
        cfg_lay.addLayout(path_row)

        # Límite de seguridad visible
        self.limits_label = QLabel(
            "ℹ️ Límite de seguridad: Hasta 100 canciones por lote · Máximo 150 MB por archivo.")
        self.limits_label.setObjectName("welcomeHint")
        self.limits_label.setStyleSheet("color: #94A3B8; font-size: 8.5pt;")
        cfg_lay.addWidget(self.limits_label)

        # Sensibilidad (calibrada entre 97.5% y 99.5%, default 98.5%)
        sens_row = QHBoxLayout()
        sens_row.addWidget(QLabel("Sensibilidad:"))
        sens_row.addWidget(QLabel("Flexible"))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.slider.setMinimumWidth(220)
        self.slider.valueChanged.connect(self._on_slider)
        sens_row.addWidget(self.slider, 1)
        sens_row.addWidget(QLabel("Estricto"))
        self.theta_label = QLabel("")
        self.theta_label.setObjectName("mutedLabel")
        sens_row.addWidget(self.theta_label)
        cfg_lay.addLayout(sens_row)

        # Botón principal + progreso
        self.analyze_btn = QPushButton("ANALIZAR UNIVERSO DE AUDIO")
        self.analyze_btn.setObjectName("btnPrimary")
        self.analyze_btn.clicked.connect(self._start_analysis)
        cfg_lay.addWidget(self.analyze_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p% · %v/%m")
        self.progress.setVisible(False)
        cfg_lay.addWidget(self.progress)

        if not self._engine_ok:
            hint = QLabel(self._engine_why)
            hint.setObjectName("welcomeHint")
            hint.setWordWrap(True)
            cfg_lay.addWidget(hint)
            self.analyze_btn.setEnabled(False)
            self.analyze_btn.setToolTip(self._engine_why)

        lay.addWidget(cfg, 0)
        self._on_slider(self.slider.value())

        # --- Resultados (vista previa antes de aplicar) -------------------
        results = QFrame()
        results.setObjectName("card")
        res_lay = QVBoxLayout(results)
        res_lay.setContentsMargins(12, 10, 12, 12)
        res_lay.setSpacing(8)

        res_head = QHBoxLayout()
        res_title = QLabel("RESULTADOS DEL ANÁLISIS")
        res_title.setObjectName("sectionHeaderTitle")
        res_head.addWidget(res_title)
        res_head.addStretch(1)

        self.copy_btn = QPushButton("📋 Copiar")
        self.copy_btn.setObjectName("logActionBtn")
        self.copy_btn.setToolTip("Copiar coincidencias detectadas al portapapeles")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_results)
        res_head.addWidget(self.copy_btn)

        self.clear_btn = QPushButton("🗑 Limpiar")
        self.clear_btn.setObjectName("logActionBtn")
        self.clear_btn.setToolTip("Limpiar resultados")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_all)
        res_head.addWidget(self.clear_btn)

        self.resume_label = QLabel("")
        self.resume_label.setObjectName("mutedLabel")
        res_head.addWidget(self.resume_label)
        res_lay.addLayout(res_head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.results_container = QWidget()
        self.results_lay = QVBoxLayout(self.results_container)
        self.results_lay.setContentsMargins(0, 0, 0, 0)
        self.results_lay.setSpacing(6)
        self.scroll.setWidget(self.results_container)
        res_lay.addWidget(self.scroll, 1)
        lay.addWidget(results, 1)

        # --- Acción final ---------------------------------------------------
        exec_row = QHBoxLayout()
        exec_row.addStretch(1)
        self.exec_btn = QPushButton("EJECUTAR GRUPOS (carpeta_N)")
        self.exec_btn.setObjectName("btnSecondary")
        self.exec_btn.setEnabled(False)
        self.exec_btn.clicked.connect(self._execute)
        exec_row.addWidget(self.exec_btn)
        lay.addLayout(exec_row)

        # Estado inicial
        self._set_status(self.last_status or "Listo", 5000)
        self._render_placeholder()
        if self.config.carpeta_base:
            self.path_edit.setText(self.config.carpeta_base)
        self._validate_limits()

    # --- Configuración --------------------------------------------------------
    def apply_config(self) -> None:
        if not self.path_edit.text().strip() and self.config.carpeta_base:
            self.path_edit.setText(self.config.carpeta_base)

    # --- Sensibilidad ---------------------------------------------------------
    def _theta(self) -> float:
        v = self.slider.value() / 100.0
        return round(_THETA_MIN + v * (_THETA_MAX - _THETA_MIN), 4)

    def _on_slider(self, value: int) -> None:
        th = self._theta()
        tag = ""
        if th >= 0.990:
            tag = "· Estricto"
        elif 0.982 <= th <= 0.988:
            tag = "· Recomendado"
        elif th <= 0.978:
            tag = "· Flexible"
        self.theta_label.setText(f"similitud ≥ {th:.1%} {tag}")

        # Recálculo al vuelo si ya se analizaron los audios
        if self._last_analysis is not None and not self._busy:
            try:
                self._plan = audio_brain.build_plan(self._last_analysis, th)
                self._render_results(self._last_analysis)
                self.exec_btn.setEnabled(len(self._plan.groups) > 0)
                self.copy_btn.setEnabled(len(self._plan.groups) > 0)
                n = len(self._plan.groups)
                self._set_status(f"{n} grupo(s) y {self._plan.singles} única(s) a {th:.1%}", 3000)
            except Exception as exc:  # noqa: BLE001
                logger.error("error recalculando plan al mover slider: %s", exc)

    def _on_path_changed(self) -> None:
        """Si el usuario cambia la ruta, limpia automáticamente los resultados y valida límites."""
        self._last_analysis = None
        self._plan = None
        self.exec_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self._render_placeholder()
        self._validate_limits()

    def _validate_limits(self) -> tuple[bool, str]:
        """Comprueba límites de seguridad: máx 100 archivos y 150 MB por archivo."""
        ruta = self.path_edit.text().strip()
        if not ruta:
            self.limits_label.setText(
                "ℹ️ Límite de seguridad: Hasta 100 canciones por lote · Máximo 150 MB por archivo.")
            self.limits_label.setStyleSheet("color: #94A3B8; font-size: 8.5pt;")
            self.analyze_btn.setEnabled(self._engine_ok)
            return True, ""

        p = Path(ruta)
        if not p.is_dir():
            self.limits_label.setText(
                "ℹ️ Límite de seguridad: Hasta 100 canciones por lote · Máximo 150 MB por archivo.")
            self.limits_label.setStyleSheet("color: #94A3B8; font-size: 8.5pt;")
            return False, f"La carpeta no existe: {p}"

        try:
            audios, _ = audio_brain.scan_folder(p, self.config.extensiones_permitidas)
        except Exception as exc:
            return False, str(exc)

        if len(audios) == 0:
            self.limits_label.setText("ℹ️ Sin archivos de audio admitidos en la carpeta.")
            self.limits_label.setStyleSheet("color: #94A3B8; font-size: 8.5pt;")
            self.analyze_btn.setEnabled(False)
            return False, "La carpeta no contiene archivos de audio admitidos."

        if len(audios) > _MAX_FILES_LIMIT:
            msg = (f"⚠️ Límite excedido: La carpeta contiene {len(audios)} canciones "
                   f"(máximo {_MAX_FILES_LIMIT} permitidas por lote). Reduce el lote para continuar.")
            self.limits_label.setText(msg)
            self.limits_label.setStyleSheet("color: #F87171; font-weight: bold; font-size: 8.5pt;")
            self.analyze_btn.setEnabled(False)
            self._set_status(msg, 5000)
            return False, msg

        for a in audios:
            try:
                sz = a.stat().st_size
                if sz > _MAX_FILE_SIZE_BYTES:
                    mb = sz / (1024 * 1024)
                    msg = (f"⚠️ Archivo demasiado grande: '{a.name}' pesa {mb:.1f} MB "
                           f"(máximo {_MAX_FILE_SIZE_MB} MB permitidos).")
                    self.limits_label.setText(msg)
                    self.limits_label.setStyleSheet("color: #F87171; font-weight: bold; font-size: 8.5pt;")
                    self.analyze_btn.setEnabled(False)
                    self._set_status(msg, 5000)
                    return False, msg
            except Exception:
                pass

        msg = f"✓ {len(audios)} archivo(s) de audio detectados dentro de los límites de seguridad."
        self.limits_label.setText(msg)
        self.limits_label.setStyleSheet("color: #10B981; font-size: 8.5pt;")
        self.analyze_btn.setEnabled(self._engine_ok)
        return True, ""

    def _clear_all(self) -> None:
        """Limpia la vista previa y los resultados en memoria."""
        self._last_analysis = None
        self._plan = None
        self.progress.setVisible(False)
        self.exec_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self._render_placeholder()
        self._set_status("Resultados limpiados.", 3000)

    def _copy_results(self) -> None:
        """Copia el resumen de coincidencias al portapapeles."""
        plan = self._plan
        if plan is None or not plan.groups:
            self._set_status("No hay grupos para copiar.", 2500)
            return
        lines = [
            f"Music-App · Grupos detectados en: {plan.root_dir.name}",
            f"Umbral de similitud: {plan.threshold:.1%}",
            f"Total grupos: {len(plan.groups)} · Archivos a agrupar: {plan.files_to_move}",
            "",
        ]
        for g in plan.groups:
            lines.append(f"📁 {g.folder_name} ({len(g.files)} archivos · {g.mean_sim:.1%} similitud):")
            for f in g.files:
                lines.append(f"   · {f.name} ({_fmt_dur(f.duration)})")
            lines.append("")
        if plan.singles:
            lines.append(f"ℹ️ {plan.singles} canciones únicas permanecen en la carpeta raíz.")
        if plan.errors:
            lines.append(f"⚠️ {len(plan.errors)} archivo(s) no se pudieron analizar.")

        text = "\n".join(lines)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            self._set_status("✓ Resultados copiados al portapapeles.", 3000)

    # --- Selección de carpeta -------------------------------------------------
    def _browse(self) -> None:
        initial = self.path_edit.text().strip() or self.config.carpeta_base or ""
        folder = QFileDialog.getExistingDirectory(self, "Carpeta a analizar", initial)
        if folder:
            self.path_edit.setText(folder)

    # --- Análisis (troceado en el bucle de eventos, sin hilos) -----------------
    def _start_analysis(self) -> None:
        ruta = self.path_edit.text().strip()
        if not ruta:
            self._set_status("Indica una carpeta a analizar primero.", 4000)
            return
        if not Path(ruta).is_dir():
            self._set_status(f"La carpeta no existe: {ruta}", 4000)
            return
        if not self._engine_ok:
            self._set_status(self._engine_why, 6000)
            return
        if self._busy:
            return

        ok, why = self._validate_limits()
        if not ok:
            return

        # Limpiar resultados anteriores antes de arrancar
        self._busy = True
        self._last_analysis = None
        self._plan = None
        self.analyze_btn.setEnabled(False)
        self.exec_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._render_placeholder()
        self.resume_label.setText("Analizando…")
        self._set_status("Analizando universo de audio…", 0)
        # El análisis corre en un hilo de fondo (ver app/ui/search_worker.py).
        self._analyzer.start(ruta, self.config.extensiones_permitidas)

    def _on_progress(self, done: int, total: int, name: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        self.resume_label.setText(f"{done}/{total} · {name}")
        if done % 2 == 0 or done == total:
            self._set_status(f"Analizando… {done}/{total}", 1200)

    def _on_analyzed(self, analysis) -> None:
        self._busy = False
        self._last_analysis = analysis
        self.analyze_btn.setEnabled(self._engine_ok)
        try:
            self._plan = audio_brain.build_plan(analysis, self._theta())
        except Exception as exc:  # noqa: BLE001
            self._on_failed(str(exc))
            return
        self.progress.setValue(self.progress.maximum())
        self._render_results(analysis)
        has_groups = len(self._plan.groups) > 0
        self.exec_btn.setEnabled(has_groups)
        self.copy_btn.setEnabled(has_groups)
        n = len(self._plan.groups)
        msg = f"{n} grupo(s) y {self._plan.singles} canción(es) única(s) detectado(s)."
        self._set_status(msg, 5000)
        logger.info("análisis: %s", msg)

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self.analyze_btn.setEnabled(self._engine_ok)
        self.progress.setVisible(False)
        self._render_placeholder()
        self._set_status(f"Fallo en el análisis: {message}", 6000)
        logger.error("fallo en el análisis: %s", message)

    # --- Vista previa -----------------------------------------------------------
    def _clear_results(self) -> None:
        while self.results_lay.count():
            item = self.results_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_placeholder(self) -> None:
        self._clear_results()
        ph = QLabel(
            "Ejecuta «ANALIZAR UNIVERSO DE AUDIO» para detectar canciones iguales "
            "o variantes (distinto ritmo/render) y agruparlas en carpetas.")
        ph.setObjectName("mutedLabel")
        ph.setWordWrap(True)
        self.results_lay.addWidget(ph)
        self.results_lay.addStretch(1)
        self.resume_label.setText("")

    def _render_results(self, analysis) -> None:
        self._clear_results()
        plan = self._plan
        if plan is None or not plan.groups:
            if plan and plan.errors and len(plan.errors) == analysis.audio_count:
                ph = QLabel(
                    f"⚠️ No se pudo analizar ningún archivo ({len(plan.errors)} con error).\n"
                    "Revisa los detalles abajo o el archivo de log.")
            else:
                ph = QLabel("No se detectaron grupos con más de un archivo. "
                            "Prueba a mover el control de sensibilidad hacia «Flexible».")
            ph.setObjectName("mutedLabel")
            ph.setWordWrap(True)
            self.results_lay.addWidget(ph)
        else:
            for g in plan.groups[: _MAX_GROUPS_SHOWN]:
                card = QFrame()
                card.setObjectName("card")
                card_lay = QVBoxLayout(card)
                card_lay.setContentsMargins(10, 8, 10, 8)
                card_lay.setSpacing(4)
                head = QLabel(
                    f"📁 {g.folder_name} · {len(g.files)} archivos · "
                    f"similitud media {g.mean_sim:.1%}")
                head.setObjectName("sectionHeaderTitle")
                card_lay.addWidget(head)
                for f in g.files:
                    card_lay.addWidget(_SongRowWidget(f, self))
                self.results_lay.addWidget(card)
            if len(plan.groups) > _MAX_GROUPS_SHOWN:
                more = QLabel(f"+ {len(plan.groups) - _MAX_GROUPS_SHOWN} grupo(s) más…")
                more.setObjectName("mutedLabel")
                self.results_lay.addWidget(more)

        # Sección de canciones únicas (se quedan en su sitio y se pueden escuchar)
        if plan and plan.singles_profiles:
            singles_card = QFrame()
            singles_card.setObjectName("card")
            singles_lay = QVBoxLayout(singles_card)
            singles_lay.setContentsMargins(10, 8, 10, 8)
            singles_lay.setSpacing(4)
            head_s = QLabel(
                f"🎵 Canciones Únicas ({len(plan.singles_profiles)} archivos · Permanecen en la raíz)")
            head_s.setObjectName("sectionHeaderTitle")
            singles_lay.addWidget(head_s)
            sub_s = QLabel("Estas canciones no tienen duplicados y no se moverán al ejecutar.")
            sub_s.setObjectName("mutedLabel")
            sub_s.setStyleSheet("font-size: 8.5pt; color: #94A3B8; margin-bottom: 2px;")
            singles_lay.addWidget(sub_s)
            for f in plan.singles_profiles[:_MAX_GROUPS_SHOWN]:
                singles_lay.addWidget(_SongRowWidget(f, self))
            if len(plan.singles_profiles) > _MAX_GROUPS_SHOWN:
                more_s = QLabel(f"+ {len(plan.singles_profiles) - _MAX_GROUPS_SHOWN} única(s) más…")
                more_s.setObjectName("mutedLabel")
                singles_lay.addWidget(more_s)
            self.results_lay.addWidget(singles_card)

        if plan and plan.errors:
            err_card = QFrame()
            err_card.setObjectName("card")
            err_lay = QVBoxLayout(err_card)
            err_lay.setContentsMargins(10, 8, 10, 8)
            err_lay.setSpacing(4)
            err_head = QLabel(f"⚠️ Archivos sin analizar ({len(plan.errors)})")
            err_head.setObjectName("sectionHeaderTitle")
            err_lay.addWidget(err_head)
            for fname, reason in plan.errors[:8]:
                row = QLabel(f"· {fname} ({reason})")
                row.setObjectName("mutedLabel")
                row.setWordWrap(True)
                err_lay.addWidget(row)
            if len(plan.errors) > 8:
                more_err = QLabel(f"+ {len(plan.errors) - 8} archivo(s) más con error…")
                more_err.setObjectName("mutedLabel")
                err_lay.addWidget(more_err)
            self.results_lay.addWidget(err_card)

        self.results_lay.addStretch(1)

        bits = []
        bits.append(f"{analysis.audio_count} audio(s) revisados")
        if plan.singles:
            bits.append(f"{plan.singles} único(s) se quedan en su sitio")
        if plan.ignored:
            bits.append(f"{len(plan.ignored)} vídeo(s) ignorado(s) (sin ffmpeg en el MVP)")
        if plan.errors:
            bits.append(f"{len(plan.errors)} sin analizar")
        self.resume_label.setText(" · ".join(bits))

    # --- Ejecución en disco ----------------------------------------------------
    def _execute(self) -> None:
        plan = self._plan
        if plan is None or not plan.groups:
            return
        solo_vista = "Los archivos se moverán dentro de la carpeta analizada. " \
            "El proceso es transaccional y conserva fecha y nombre originales."
        resp = QMessageBox.question(
            self, "Confirmar agrupación",
            f"Se crearán {len(plan.groups)} carpeta(s) y se moverán "
            f"{plan.files_to_move} archivo(s) coincidentes.\n\n"
            f"Las {plan.singles} canciones únicas permanecerán intactas en su sitio.\n\n" + solo_vista,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes:
            return
        self.exec_btn.setEnabled(False)
        self._set_status("Creando carpetas y moviendo archivos…", 0)
        QApplication.processEvents()  # pintar antes del trabajo IO
        try:
            t0 = time.monotonic()
            result = audio_brain.execute_group_plan(plan)
        except Exception as exc:  # noqa: BLE001
            logger.exception("fallo al ejecutar plan")
            self._set_status(f"Fallo al ejecutar: {exc}", 6000)
            return
        grupos = ", ".join(result["groups"])
        done = (f"{result['moved']} archivo(s) movidos a {grupos} "
                f"en {time.monotonic() - t0:.1f}s")
        self.engine_badge.setText("✓ " + done)
        self.engine_badge.setToolTip("")
        self.resume_label.setText(done)
        self._set_status(done, 6000)

    # --- Utilidad ---------------------------------------------------------------
    def _set_status(self, text: str, timeout: int = 0) -> None:
        self.last_status = text
        self.statusMessage.emit(text, timeout)