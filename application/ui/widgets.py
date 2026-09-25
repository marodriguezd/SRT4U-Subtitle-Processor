# application/ui/widgets.py
"""
Componentes visuales Glassmorphism según el mockup de SRT4U con alto contraste y diseño responsivo.
"""
import os
import math
from typing import Optional, List
from PyQt6.QtCore import Qt, QRect, QRectF, QSize, pyqtSignal, QUrl, QPoint, QEvent
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPaintEvent
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QAbstractButton,
    QScrollArea,
    QSlider,
    QDialog,
    QPlainTextEdit,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from .styles import Styles
from ..services.subtitle_service import SubtitleItem


class ModernToggle(QAbstractButton):
    """
    Switch redondeado moderno estilo iOS / macOS con acento índigo y alto contraste.
    """
    def __init__(self, parent=None, checked=False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(48, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h / 2

        if self.isChecked():
            bg_color = QColor("#6366F1")
        else:
            bg_color = QColor("#334155")

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(0, 0, w, h, radius, radius)

        # Círculo blanco (Knob)
        knob_size = h - 6
        knob_x = (w - knob_size - 3) if self.isChecked() else 3
        knob_y = 3

        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawEllipse(int(knob_x), int(knob_y), int(knob_size), int(knob_size))
        p.end()

    def hitButton(self, pos: QPoint) -> bool:
        return self.rect().contains(pos)


class LogoBadge(QWidget):
    """
    Insignia de logo violeta con icono de documento y texto SRT.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(42, 42)

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fondo degradado violeta
        rect = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#6366F1")))
        p.drawRoundedRect(rect, 10, 10)

        # Texto SRT blanco
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "SRT")
        p.end()


class CircularProgress(QWidget):
    """
    Indicador de progreso circular con porcentaje central y tiempo estimado.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 130)
        self.progress = 0.0

    def set_progress(self, val: float):
        self.progress = max(0.0, min(1.0, val))
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(12, 12, self.width() - 24, self.height() - 24)
        pen_width = 8

        # Anillo de fondo
        bg_pen = QPen(QColor("#1E293B"), pen_width)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bg_pen)
        p.drawEllipse(rect)

        # Anillo activo
        fg_pen = QPen(QColor("#6366F1"), pen_width)
        fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(fg_pen)

        start_angle = 90 * 16
        span_angle = -int(self.progress * 360 * 16)
        p.drawArc(rect, start_angle, span_angle)

        # Porcentaje
        p.setPen(QColor("#F8FAFC"))
        p.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        text = f"{int(self.progress * 100)}%"
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class ProgressModal(QDialog):
    """
    Modal de 'Procesamiento en curso' con gráfico circular y lista de etapas.
    """
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Procesamiento en curso")
        self.setFixedSize(500, 360)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #0E1526;
                border: 2px solid #6366F1;
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Header
        h_layout = QHBoxLayout()
        title = QLabel("Procesamiento en curso")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #F8FAFC;")
        h_layout.addWidget(title)
        h_layout.addStretch()
        layout.addLayout(h_layout)

        # Body: Checklist (Left) & Circular Progress (Right)
        body_layout = QHBoxLayout()
        body_layout.setSpacing(20)

        steps_box = QVBoxLayout()
        steps_box.setSpacing(10)
        self.step_labels = [
            QLabel("⌛ Leyendo archivo..."),
            QLabel("⌛ Analizando subtítulos..."),
            QLabel("⌛ Limpiando contenido no deseado..."),
            QLabel("⌛ Traduciendo..."),
            QLabel("⌛ Aplicando formato original..."),
            QLabel("⌛ Guardando archivo..."),
        ]
        for lbl in self.step_labels:
            lbl.setStyleSheet("font-size: 13px; color: #94A3B8;")
            steps_box.addWidget(lbl)
        body_layout.addLayout(steps_box, stretch=3)

        right_box = QVBoxLayout()
        right_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.circle = CircularProgress()
        self.lbl_time = QLabel("Tiempo restante: --:--")
        self.lbl_time.setStyleSheet("font-size: 12px; color: #94A3B8; margin-top: 6px;")
        right_box.addWidget(self.circle)
        right_box.addWidget(self.lbl_time)
        body_layout.addLayout(right_box, stretch=2)

        layout.addLayout(body_layout)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #1E293B;
                color: #CBD5E1;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 18px;
                font-weight: 600;
            }
            QPushButton:hover { background: #334155; color: #FFFFFF; }
        """)
        btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(btn_cancel, alignment=Qt.AlignmentFlag.AlignRight)

    def update_step(self, step_idx: int, done: bool = True, text_override: str = ""):
        if 0 <= step_idx < len(self.step_labels):
            lbl = self.step_labels[step_idx]
            original_text = text_override or lbl.text().lstrip("✓⌛◯ ")
            if done:
                lbl.setText(f"✓ {original_text}")
                lbl.setStyleSheet("font-size: 13px; color: #10B981; font-weight: 600;")
            else:
                lbl.setText(f"◯ {original_text}")
                lbl.setStyleSheet("font-size: 13px; color: #818CF8; font-weight: 600;")

    def set_progress(self, ratio: float, remaining_seconds: int = 0):
        self.circle.set_progress(ratio)
        m = remaining_seconds // 60
        s = remaining_seconds % 60
        self.lbl_time.setText(f"Tiempo restante: {m:02d}:{s:02d}")

    def _on_cancel(self):
        self.cancelled.emit()
        self.reject()


class DropZone(QFrame):
    """
    Área interactiva para arrastrar y soltar subtítulos con alto contraste y feedback visual.
    """
    file_dropped = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(160)

        self.current_subtitle_path: Optional[str] = None
        self.current_video_path: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        # Icono de carpeta estilizado
        self.icon_badge = QLabel("📁")
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_badge.setStyleSheet("font-size: 34px; color: #818CF8; background: transparent;")

        self.title_label = QLabel("Arrastra tu archivo de subtítulos aquí")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #F8FAFC; background: transparent;")

        self.sub_label = QLabel("o haz clic para seleccionar")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_label.setStyleSheet("font-size: 13px; color: #94A3B8; background: transparent;")

        self.formats_label = QLabel("Formatos soportados: .srt, .ass, .vtt, .txt")
        self.formats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.formats_label.setStyleSheet("font-size: 11px; color: #64748B; margin-top: 4px; background: transparent;")

        layout.addWidget(self.icon_badge)
        layout.addWidget(self.title_label)
        layout.addWidget(self.sub_label)
        layout.addWidget(self.formats_label)

    def set_file(self, file_path: str, video_path: Optional[str] = None):
        self.current_subtitle_path = file_path
        self.current_video_path = video_path or self._find_matching_video(file_path)

        filename = os.path.basename(file_path)
        size_kb = os.path.getsize(file_path) / 1024 if os.path.exists(file_path) else 0

        self.icon_badge.setText("📄")
        self.title_label.setText(filename)
        status_text = f"Tamaño: {size_kb:.1f} KB"
        if self.current_video_path:
            status_text += f" | Video detectado: {os.path.basename(self.current_video_path)}"

        self.sub_label.setText(status_text)
        self.sub_label.setStyleSheet("font-size: 12px; color: #38BDF8; font-weight: 500;")
        self.formats_label.setText("Haz clic o arrastra otro archivo para reemplazar")
        self.file_dropped.emit(self.current_subtitle_path, self.current_video_path or "")

    def _find_matching_video(self, sub_path: str) -> Optional[str]:
        base, _ = os.path.splitext(sub_path)
        for ext in [".mp4", ".mkv", ".webm", ".avi", ".mov"]:
            candidate = base + ext
            if os.path.exists(candidate):
                return candidate
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Seleccionar subtítulo",
                "",
                "Subtítulos (*.srt *.ass *.vtt *.txt);;Todos los archivos (*.*)"
            )
            if file_path:
                self.set_file(file_path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        sub_file = None
        video_file = None
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext in [".srt", ".ass", ".vtt", ".ssa", ".txt"]:
                sub_file = path
            elif ext in [".mp4", ".mkv", ".webm", ".avi", ".mov"]:
                video_file = path

        if sub_file:
            self.set_file(sub_file, video_file)
        elif video_file and self.current_subtitle_path:
            self.set_file(self.current_subtitle_path, video_file)


class OptionCard(QFrame):
    """
    Tarjeta de opción compacta para cuadrícula 2x2 con colores nítidos.
    """
    def __init__(self, title: str, description: str, toggle: ModernToggle, parent=None):
        super().__init__(parent)
        self.setObjectName("CardContainer")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #F8FAFC;")
        d_lbl = QLabel(description)
        d_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")

        text_layout.addWidget(t_lbl)
        text_layout.addWidget(d_lbl)

        layout.addLayout(text_layout)
        layout.addStretch()
        layout.addWidget(toggle)


class MetricCard(QFrame):
    def __init__(self, icon_str: str, value_str: str, label_str: str, parent=None):
        super().__init__(parent)
        self.setObjectName("CardContainer")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        icon_lbl = QLabel(icon_str)
        icon_lbl.setStyleSheet("font-size: 22px; color: #6366F1;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_lbl = QLabel(value_str)
        self.value_lbl.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.desc_lbl = QLabel(label_str)
        self.desc_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(icon_lbl)
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.desc_lbl)

    def set_value(self, val: str):
        self.value_lbl.setText(val)


class SubtitleCard(QFrame):
    jump_clicked = pyqtSignal(int)
    text_changed = pyqtSignal()

    def __init__(self, original_item: SubtitleItem, edited_item: SubtitleItem, parent=None):
        super().__init__(parent)
        self.original_item = original_item
        self.edited_item = edited_item
        self.is_active = False

        self.setObjectName("SubtitleCard")
        self._apply_style(active=False)
        self._setup_ui()

    def _apply_style(self, active: bool):
        if active:
            self.setStyleSheet("""
                QFrame#SubtitleCard {
                    background-color: #1A1C38;
                    border: 2px solid #8B5CF6;
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#SubtitleCard {
                    background-color: #111827;
                    border: 1px solid #1F2937;
                    border-radius: 8px;
                }
                QFrame#SubtitleCard:hover {
                    border-color: #38BDF8;
                    background-color: #141E33;
                }
            """)

    def set_active(self, active: bool):
        if self.is_active == active:
            return
        self.is_active = active
        self._apply_style(active)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header / Meta row
        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(8)

        # Index badge
        idx_lbl = QLabel(f"#{self.edited_item.index}")
        idx_lbl.setStyleSheet("""
            QLabel {
                background: #1E1B4B;
                color: #A78BFA;
                font-weight: 800;
                font-size: 11px;
                padding: 2px 7px;
                border-radius: 5px;
                border: 1px solid #3B3878;
            }
        """)
        meta_layout.addWidget(idx_lbl)

        # Time range
        time_str = self.edited_item.get_srt_time()
        time_lbl = QLabel(f"⏱ {time_str}")
        time_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #94A3B8; font-weight: 600;")
        meta_layout.addWidget(time_lbl)

        # Duration
        dur_s = max(0.0, (self.edited_item.end_ms - self.edited_item.start_ms) / 1000.0)
        dur_lbl = QLabel(f"({dur_s:.1f}s)")
        dur_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        meta_layout.addWidget(dur_lbl)

        meta_layout.addStretch()

        # Jump button
        btn_jump = QPushButton("▶ Saltar a vídeo")
        btn_jump.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_jump.setStyleSheet("""
            QPushButton {
                background: rgba(99, 102, 241, 0.15);
                color: #A5B4FC;
                border: 1px solid rgba(99, 102, 241, 0.35);
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #6366F1;
                color: #FFFFFF;
                border-color: #6366F1;
            }
        """)
        btn_jump.clicked.connect(lambda: self.jump_clicked.emit(self.edited_item.start_ms))
        meta_layout.addWidget(btn_jump)

        layout.addLayout(meta_layout)

        # Body row (Paired horizontally: Original left, Editable right)
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)

        # Left column (Original)
        left_col = QVBoxLayout()
        left_col.setSpacing(3)
        lbl_orig_tag = QLabel("ORIGINAL")
        lbl_orig_tag.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B; letter-spacing: 0.5px;")
        left_col.addWidget(lbl_orig_tag)

        orig_txt = self.original_item.text if self.original_item else ""
        self.lbl_orig = QLabel(orig_txt)
        self.lbl_orig.setWordWrap(True)
        self.lbl_orig.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_orig.setStyleSheet("""
            QLabel {
                background: #0B0F19;
                border: 1px solid #1E293B;
                border-radius: 6px;
                padding: 6px 8px;
                color: #94A3B8;
                font-size: 13px;
                line-height: 1.4;
            }
        """)
        left_col.addWidget(self.lbl_orig, stretch=1)
        body_layout.addLayout(left_col, stretch=1)

        # Right column (Editable translation)
        right_col = QVBoxLayout()
        right_col.setSpacing(3)
        lbl_edit_tag = QLabel("TRADUCCIÓN / EDICIÓN ✏️")
        lbl_edit_tag.setStyleSheet("font-size: 10px; font-weight: 700; color: #10B981; letter-spacing: 0.5px;")
        right_col.addWidget(lbl_edit_tag)

        self.edit_text = QPlainTextEdit()
        self.edit_text.setPlainText(self.edited_item.text)
        self.edit_text.setTabChangesFocus(True)
        line_count = max(1, self.edited_item.text.count('\n') + 1)
        self.edit_text.setFixedHeight(max(40, min(140, line_count * 22 + 18)))
        self.edit_text.setStyleSheet("""
            QPlainTextEdit {
                background: #080D1A;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #F8FAFC;
                font-size: 13px;
                padding: 5px 7px;
            }
            QPlainTextEdit:focus {
                border-color: #8B5CF6;
                background: #0E1528;
            }
        """)
        self.edit_text.textChanged.connect(self._on_text_changed)
        right_col.addWidget(self.edit_text, stretch=1)
        body_layout.addLayout(right_col, stretch=1)

        layout.addLayout(body_layout)

    def _on_text_changed(self):
        new_text = self.edit_text.toPlainText()
        self.edited_item.text = new_text
        line_count = max(1, new_text.count('\n') + 1)
        self.edit_text.setFixedHeight(max(40, min(140, line_count * 22 + 18)))
        self.text_changed.emit()

    def matches_query(self, query: str) -> bool:
        if not query:
            return True
        q = query.lower()
        orig = self.original_item.text.lower() if self.original_item else ""
        edit = self.edited_item.text.lower()
        return q in orig or q in edit


class SubtitleDiffViewer(QWidget):
    cue_selected = pyqtSignal(int)
    subtitles_edited = pyqtSignal(list)
    count_changed = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_items: List[SubtitleItem] = []
        self.processed_items: List[SubtitleItem] = []
        self.cards: List[SubtitleCard] = []
        self.active_card: Optional[SubtitleCard] = None
        self._current_filter: str = ""

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #1E293B;
                border-radius: 10px;
                background-color: #070B14;
            }
        """)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        layout.addWidget(self.scroll_area)

    def load_subtitles(self, original_items: List[SubtitleItem], processed_items: List[SubtitleItem]):
        self.original_items = original_items or []
        self.processed_items = processed_items or []
        self.active_card = None

        self.cards_container.setUpdatesEnabled(False)
        try:
            while self.cards_layout.count() > 1:
                child = self.cards_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            self.cards.clear()

            orig_map = {item.index: item for item in self.original_items}
            for idx, proc_item in enumerate(self.processed_items):
                orig_item = orig_map.get(proc_item.index)
                if orig_item is None and idx < len(self.original_items):
                    orig_item = self.original_items[idx]
                if orig_item is None:
                    orig_item = proc_item

                card = SubtitleCard(orig_item, proc_item)
                card.jump_clicked.connect(self.cue_selected.emit)
                card.text_changed.connect(self._on_card_edited)
                self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
                self.cards.append(card)
        finally:
            self.cards_container.setUpdatesEnabled(True)

        if self._current_filter:
            self.filter_subtitles(self._current_filter)
        else:
            self.count_changed.emit(len(self.cards), len(self.cards))

    def _on_card_edited(self):
        self.subtitles_edited.emit(self.processed_items)

    def get_processed_subtitles(self) -> List[SubtitleItem]:
        return self.processed_items

    def highlight_cue_at_ms(self, pos_ms: int, auto_scroll: bool = True):
        matching_card = None
        for card in self.cards:
            if card.edited_item.start_ms <= pos_ms <= card.edited_item.end_ms:
                matching_card = card
                break

        if matching_card != self.active_card:
            if self.active_card:
                self.active_card.set_active(False)
            self.active_card = matching_card
            if self.active_card:
                self.active_card.set_active(True)
                if auto_scroll and self.active_card.isVisible():
                    self.scroll_area.ensureWidgetVisible(self.active_card, 0, 70)

    def filter_subtitles(self, query: str) -> tuple[int, int]:
        self._current_filter = query.strip()
        visible_count = 0
        total_count = len(self.cards)

        self.cards_container.setUpdatesEnabled(False)
        try:
            for card in self.cards:
                matches = card.matches_query(self._current_filter)
                card.setVisible(matches)
                if matches:
                    visible_count += 1
        finally:
            self.cards_container.setUpdatesEnabled(True)

        self.count_changed.emit(visible_count, total_count)
        return visible_count, total_count


class VideoPreviewPlayer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #070B14; border-radius: 12px; border: 1px solid #25304B;")
        self.setMinimumHeight(180)
        self.setAcceptDrops(True)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0)
        self.player.setAudioOutput(self.audio_output)
        self.player.tracksChanged.connect(self._on_tracks_changed)
        self.current_subtitles: List[SubtitleItem] = []

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.video_container = QWidget()
        v_layout = QVBoxLayout(self.video_container)
        v_layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget()
        self.player.setVideoOutput(self.video_widget)
        v_layout.addWidget(self.video_widget)

        self.sub_overlay = QLabel(
            "Haz clic aquí o arrastra un video (.mp4, .mkv, .webm) para previsualizar",
            self.video_container
        )
        self.sub_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_overlay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sub_overlay.setWordWrap(True)
        self.sub_overlay.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.88);
                color: #FFFFFF;
                font-size: 14px;
                font-weight: 700;
                padding: 6px 16px;
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
        """)
        self.sub_overlay.mousePressEvent = lambda e: self._browse_video() if (not self.player.source().isValid() or self.player.source().isEmpty()) else None
        
        self.video_container.installEventFilter(self)
        self.video_widget.installEventFilter(self)
        layout.addWidget(self.video_container)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(4, 0, 4, 0)
        ctrl_layout.setSpacing(10)

        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(32, 32)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background: #6366F1;
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background: #4F46E5; }
        """)

        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #1E293B; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #6366F1; border-radius: 2px; }
            QSlider::handle:horizontal { width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: #FFFFFF; }
        """)

        self.time_lbl = QLabel("00:00:00 / 00:00:00")
        self.time_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-family: monospace;")

        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setFixedSize(28, 28)
        self.btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mute.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
        """)
        self.btn_mute.clicked.connect(self._toggle_mute)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(70)
        self.vol_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #1E293B; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #10B981; border-radius: 2px; }
            QSlider::handle:horizontal { width: 10px; height: 10px; margin: -3px 0; border-radius: 5px; background: #FFFFFF; }
        """)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)

        self.btn_load_video = QPushButton("🎬 Cargar vídeo")
        self.btn_load_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_video.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: #E2E8F0;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(99, 102, 241, 0.25);
                border-color: #818CF8;
                color: #FFFFFF;
            }
        """)
        self.btn_load_video.clicked.connect(self._browse_video)

        ctrl_layout.addWidget(self.play_btn)
        ctrl_layout.addWidget(self.time_slider)
        ctrl_layout.addWidget(self.time_lbl)
        ctrl_layout.addWidget(self.btn_mute)
        ctrl_layout.addWidget(self.vol_slider)
        ctrl_layout.addWidget(self.btn_load_video)
        layout.addLayout(ctrl_layout)

    def _on_tracks_changed(self):
        if len(self.player.audioTracks()) > 0 and self.player.activeAudioTrack() == -1:
            self.player.setActiveAudioTrack(0)

    def _on_volume_changed(self, val: int):
        vol = val / 100.0
        self.audio_output.setVolume(vol)
        if val == 0:
            self.btn_mute.setText("🔇")
        elif val < 50:
            self.btn_mute.setText("🔉")
        else:
            self.btn_mute.setText("🔊")

    def _toggle_mute(self):
        is_muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not is_muted)
        if not is_muted:
            self.btn_mute.setText("🔇")
        else:
            val = self.vol_slider.value()
            self.btn_mute.setText("🔊" if val >= 50 else "🔉")

    def eventFilter(self, watched, event):
        if watched in (self.video_container, self.video_widget) and event.type() == QEvent.Type.Resize:
            self._reposition_overlay()
        return super().eventFilter(watched, event)

    def _reposition_overlay(self):
        w = self.video_container.width()
        h = self.video_container.height()
        if w <= 0 or h <= 0:
            return
        self.sub_overlay.adjustSize()
        sh = self.sub_overlay.sizeHint()
        lbl_w = min(max(260, sh.width() + 32), max(100, w - 24))
        lbl_h = max(34, min(80, sh.height()))
        lbl_x = (w - lbl_w) // 2
        lbl_y = max(8, h - lbl_h - 14)
        self.sub_overlay.setGeometry(lbl_x, lbl_y, lbl_w, lbl_h)
        self.sub_overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlay()

    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar vídeo para previsualizar",
            "",
            "Archivos de vídeo (*.mp4 *.mkv *.webm *.avi *.mov *.flv *.m4v);;Todos los archivos (*.*)"
        )
        if path:
            self.load_video(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext in ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.m4v']:
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.m4v']:
                    self.load_video(file_path)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    def _connect_signals(self):
        self.play_btn.clicked.connect(self._toggle_playback)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.time_slider.sliderMoved.connect(self._set_position)

    def load_video(self, video_path: str):
        if os.path.exists(video_path):
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.sub_overlay.setText("Video cargado - Listo para reproducir")
            self._reposition_overlay()
            self.sub_overlay.show()
            self.sub_overlay.raise_()

    def set_subtitles(self, subtitles: List[SubtitleItem]):
        self.current_subtitles = subtitles
        # Update current overlay text based on current position
        if self.player.position() > 0:
            self._on_position_changed(self.player.position())

    def seek_to_ms(self, ms: int):
        was_playing = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self.player.setPosition(ms)
        self._on_position_changed(ms)
        if was_playing:
            self.player.play()

    def _toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_btn.setText("▶")
        else:
            self.player.play()
            self.play_btn.setText("⏸")

    def _on_duration_changed(self, duration: int):
        self.time_slider.setRange(0, duration)
        self._update_time_label(self.player.position(), duration)

    def _on_position_changed(self, pos: int):
        if not self.time_slider.isSliderDown():
            self.time_slider.setValue(pos)
        self._update_time_label(pos, self.player.duration())

        active_lines = []
        for item in self.current_subtitles:
            if item.start_ms <= pos <= item.end_ms:
                txt = item.text.strip()
                if txt and txt not in active_lines:
                    active_lines.append(txt)
        active_text = "\n".join(active_lines)

        if active_text:
            self.sub_overlay.setText(active_text)
            self._reposition_overlay()
            self.sub_overlay.show()
            self.sub_overlay.raise_()
        else:
            if self.player.source().isValid() and not self.player.source().isEmpty():
                self.sub_overlay.setText("")
                self.sub_overlay.hide()
            else:
                self.sub_overlay.setText("Haz clic aquí o arrastra un video (.mp4, .mkv, .webm) para previsualizar")
                self._reposition_overlay()
                self.sub_overlay.show()
                self.sub_overlay.raise_()

    def _set_position(self, pos: int):
        self.player.setPosition(pos)

    def _update_time_label(self, pos: int, dur: int):
        cur_str = self._format_ms(pos)
        dur_str = self._format_ms(dur)
        self.time_lbl.setText(f"{cur_str} / {dur_str}")

    def _format_ms(self, ms: int) -> str:
        s = (ms // 1000) % 60
        m = (ms // 60000) % 60
        h = (ms // 3600000)
        return f"{h:02d}:{m:02d}:{s:02d}"
