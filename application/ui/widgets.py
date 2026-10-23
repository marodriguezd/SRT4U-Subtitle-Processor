"""
Glassmorphism visual components matching the SRT4U mockup with high contrast and responsive layout.
"""

import os
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from typing import Optional, List
from PyQt6.QtCore import Qt, QRectF, QSize, pyqtSignal, QUrl, QPoint, QEvent
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPaintEvent
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QAbstractButton,
    QScrollArea,
    QSlider,
    QDialog,
    QPlainTextEdit,
)

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget

    MULTIMEDIA_AVAILABLE = True
except (ImportError, OSError):
    QMediaPlayer = None  # type: ignore[assignment,misc]
    QAudioOutput = None  # type: ignore[assignment,misc]
    QVideoWidget = None  # type: ignore[assignment,misc]
    MULTIMEDIA_AVAILABLE = False

from .icons import Icons
from .styles import Styles, sync_minimum_size
from .file_dialogs import ask_open_file
from ..services.subtitle_service import SubtitleItem
from ..services.i18n_service import t


class ModernToggle(QAbstractButton):
    """Modern rounded toggle switch in iOS/macOS style with indigo accent and high contrast."""

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
            bg_color = QColor(Styles.PRIMARY)
        else:
            bg_color = QColor(Styles.BORDER)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(0, 0, w, h, radius, radius)

        knob_size = h - 6
        knob_x = (w - knob_size - 3) if self.isChecked() else 3
        knob_y = 3

        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawEllipse(int(knob_x), int(knob_y), int(knob_size), int(knob_size))
        p.end()

    def hitButton(self, pos: QPoint) -> bool:
        return self.rect().contains(pos)


class LogoBadge(QWidget):
    """Violet logo badge with document icon and SRT label."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(42, 42)

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(Styles.PRIMARY)))
        p.drawRoundedRect(rect, 10, 10)

        p.setPen(QColor("#FFFFFF"))
        p.setFont(Styles.ui_font(12, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "SRT")
        p.end()


class CircularProgress(QWidget):
    """Circular progress indicator with central percentage and estimated time."""

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

        bg_pen = QPen(QColor(Styles.SURFACE_RAISED), pen_width)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bg_pen)
        p.drawEllipse(rect)

        fg_pen = QPen(QColor(Styles.PRIMARY), pen_width)
        fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(fg_pen)

        start_angle = 90 * 16
        span_angle = -int(self.progress * 360 * 16)
        p.drawArc(rect, start_angle, span_angle)

        p.setPen(QColor(Styles.TEXT))
        p.setFont(Styles.ui_font(18, QFont.Weight.Bold))
        text = f"{int(self.progress * 100)}%"
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class ProgressModal(QDialog):
    """In-progress modal dialog with circular progress chart and stage checklist."""

    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("progress.window_title"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: #0E1526;
                border: 2px solid {Styles.PRIMARY};
                border-radius: 16px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        h_layout = QHBoxLayout()
        title = QLabel(t("progress.title"))
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {Styles.TEXT};")
        h_layout.addWidget(title)
        h_layout.addStretch()
        layout.addLayout(h_layout)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(20)

        steps_box = QVBoxLayout()
        steps_box.setSpacing(10)
        self._step_texts = [
            t("progress.step_reading"),
            t("progress.step_analyzing"),
            t("progress.step_cleaning"),
            t("progress.step_translating"),
            t("progress.step_formatting"),
            t("progress.step_saving"),
        ]
        self.step_labels = [QLabel(text) for text in self._step_texts]
        for lbl in self.step_labels:
            lbl.setStyleSheet(f"font-size: 13px; color: {Styles.TEXT_MUTED};")
            steps_box.addWidget(lbl)
        body_layout.addLayout(steps_box, stretch=3)

        right_box = QVBoxLayout()
        right_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.circle = CircularProgress()
        self.lbl_time = QLabel(t("progress.remaining", time="--:--"))
        self.lbl_time.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_MUTED}; margin-top: 6px;"
        )
        right_box.addWidget(self.circle)
        right_box.addWidget(self.lbl_time)
        body_layout.addLayout(right_box, stretch=2)

        layout.addLayout(body_layout)

        btn_cancel = QPushButton(t("progress.cancel"))
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: {Styles.SURFACE_RAISED};
                color: {Styles.TEXT_SUBTLE};
                border: 1px solid {Styles.BORDER};
                border-radius: 8px;
                padding: 8px 18px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {Styles.BORDER}; color: #FFFFFF; }}
        """)
        btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(btn_cancel, alignment=Qt.AlignmentFlag.AlignRight)
        sync_minimum_size(self, QSize(500, 360))
        self.resize(self.minimumSize())

    def update_step(self, step_idx: int, done: bool = True, text_override: str = ""):
        if 0 <= step_idx < len(self.step_labels):
            lbl = self.step_labels[step_idx]
            lbl.setText(text_override or self._step_texts[step_idx])
            if done:
                lbl.setStyleSheet(
                    f"font-size: 13px; color: {Styles.SUCCESS}; font-weight: 600;"
                )
            else:
                lbl.setStyleSheet("font-size: 13px; color: #818CF8; font-weight: 600;")

    def set_progress(self, ratio: float, remaining_seconds: int = 0):
        self.circle.set_progress(ratio)
        m = remaining_seconds // 60
        s = remaining_seconds % 60
        self.lbl_time.setText(t("progress.remaining", time=f"{m:02d}:{s:02d}"))

    def _on_cancel(self):
        self.cancelled.emit()
        self.reject()


class DropZone(QFrame):
    """Interactive drag-and-drop area for subtitles and media with visual feedback."""

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

        self.icon_badge = QLabel()
        self.icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_badge.setStyleSheet("background: transparent;")

        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Styles.TEXT}; background: transparent;"
        )

        self.sub_label = QLabel()
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_label.setWordWrap(True)
        self.sub_label.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED}; background: transparent;"
        )

        self.formats_label = QLabel()
        self.formats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.formats_label.setWordWrap(True)
        self.formats_label.setStyleSheet(
            f"font-size: 11px; color: {Styles.TEXT_FAINT}; margin-top: 4px; background: transparent;"
        )

        layout.addWidget(self.icon_badge)
        layout.addWidget(self.title_label)
        layout.addWidget(self.sub_label)
        layout.addWidget(self.formats_label)
        self.retranslate()

    def retranslate(self):
        if not self.current_subtitle_path:
            self.icon_badge.setPixmap(
                Icons.get_pixmap("folder", color="#818CF8", size=42)
            )
            self.title_label.setText(t("dropzone.title"))
            self.sub_label.setText(t("dropzone.subtitle"))
            self.sub_label.setStyleSheet(
                f"font-size: 13px; color: {Styles.TEXT_MUTED}; background: transparent;"
            )
            self.formats_label.setText(t("dropzone.formats"))
        else:
            filename = os.path.basename(self.current_subtitle_path)
            size_kb = (
                os.path.getsize(self.current_subtitle_path) / 1024
                if os.path.exists(self.current_subtitle_path)
                else 0
            )
            self.icon_badge.setPixmap(
                Icons.get_pixmap("file", color="#38BDF8", size=42)
            )
            self.title_label.setText(filename)
            status_text = t("dropzone.size", size=size_kb)
            if self.current_video_path:
                status_text += " | " + t(
                    "dropzone.video_detected",
                    name=os.path.basename(self.current_video_path),
                )
            self.sub_label.setText(status_text)
            self.sub_label.setStyleSheet(
                f"font-size: 12px; color: {Styles.INFO}; font-weight: 500;"
            )
            self.formats_label.setText(t("dropzone.replace_hint"))

    def set_file(self, file_path: str, video_path: Optional[str] = None):
        self.current_subtitle_path = file_path
        self.current_video_path = video_path or self._find_matching_video(file_path)
        self.retranslate()
        self.file_dropped.emit(
            self.current_subtitle_path, self.current_video_path or ""
        )

    def _find_matching_video(self, sub_path: str) -> Optional[str]:
        base, _ = os.path.splitext(sub_path)
        for ext in [".mp4", ".mkv", ".webm", ".avi", ".mov"]:
            candidate = base + ext
            if os.path.exists(candidate):
                return candidate
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            file_path = ask_open_file(
                self, t("dropzone.dialog_title"), t("dropzone.filter")
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
    """Compact option card with toggle switch for grid layouts."""

    def __init__(self, title: str, description: str, toggle: ModernToggle, parent=None):
        super().__init__(parent)
        self.setObjectName("CardContainer")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        self.t_lbl = QLabel(title)
        self.t_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {Styles.TEXT};"
        )
        self.t_lbl.setWordWrap(True)
        self.d_lbl = QLabel(description)
        self.d_lbl.setStyleSheet(f"font-size: 12px; color: {Styles.TEXT_MUTED};")
        self.d_lbl.setWordWrap(True)

        text_layout.addWidget(self.t_lbl)
        text_layout.addWidget(self.d_lbl)

        layout.addLayout(text_layout)
        layout.addStretch()
        layout.addWidget(toggle)

    def set_texts(self, title: str, description: str):
        self.t_lbl.setText(title)
        self.d_lbl.setText(description)


class MetricCard(QFrame):
    def __init__(self, icon_str: str, value_str: str, label_str: str, parent=None):
        super().__init__(parent)
        self.setObjectName("CardContainer")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        self.icon_lbl = QLabel()
        self.icon_lbl.setStyleSheet("background: transparent;")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_icon(icon_str)

        self.value_lbl = QLabel(value_str)
        self.value_lbl.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.desc_lbl = QLabel(label_str)
        self.desc_lbl.setStyleSheet(f"font-size: 12px; color: {Styles.TEXT_MUTED};")
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.desc_lbl)

    def set_icon(self, icon_str: str):
        icon_name = _METRIC_ICONS.get(icon_str, "file")
        self.icon_lbl.setPixmap(Icons.get_pixmap(icon_name, color="#818CF8", size=24))

    def set_value(self, val: str):
        self.value_lbl.setText(val)

    def set_label(self, lbl: str):
        self.desc_lbl.setText(lbl)


_METRIC_ICONS = {
    "file": "file",
    "clean": "clean",
    "clock": "clock",
    "zap": "zap",
    "check": "check",
    "folder": "folder",
}


class SubtitleCard(QFrame):
    jump_clicked = pyqtSignal(int)
    text_changed = pyqtSignal()

    def __init__(
        self, original_item: SubtitleItem, edited_item: SubtitleItem, parent=None
    ):
        super().__init__(parent)
        self.original_item = original_item
        self.edited_item = edited_item
        self.is_active = False

        self.setObjectName("SubtitleCard")
        self._apply_style(active=False)
        self._setup_ui()

    def _apply_style(self, active: bool):
        if active:
            self.setStyleSheet(f"""
                QFrame#SubtitleCard {{
                    background-color: #1A1C38;
                    border: 2px solid {Styles.ACCENT};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#SubtitleCard {{
                    background-color: {Styles.SURFACE_ALT};
                    border: 1px solid {Styles.BORDER_SUBTLE};
                    border-radius: 8px;
                }}
                QFrame#SubtitleCard:hover {{
                    border-color: {Styles.INFO};
                    background-color: #141E33;
                }}
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

        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(8)

        idx_lbl = QLabel(f"#{self.edited_item.index}")
        idx_lbl.setStyleSheet(f"""
            QLabel {{
                background: #1E1B4B;
                color: {Styles.ACCENT_LIGHT};
                font-weight: 800;
                font-size: 11px;
                padding: 2px 7px;
                border-radius: 5px;
                border: 1px solid #3B3878;
            }}
        """)
        meta_layout.addWidget(idx_lbl)

        time_str = self.edited_item.get_srt_time()
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(
            f"font-family: monospace; font-size: 11px; color: {Styles.TEXT_MUTED}; font-weight: 600;"
        )
        meta_layout.addWidget(time_lbl)

        dur_s = max(0.0, (self.edited_item.end_ms - self.edited_item.start_ms) / 1000.0)
        dur_lbl = QLabel(f"({dur_s:.1f}s)")
        dur_lbl.setStyleSheet(f"font-size: 11px; color: {Styles.TEXT_FAINT};")
        meta_layout.addWidget(dur_lbl)

        meta_layout.addStretch()

        self.btn_jump = QPushButton(t("preview.btn_jump"))
        self.btn_jump.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_jump.setStyleSheet(f"""
            QPushButton {{
                background: rgba(99, 102, 241, 0.15);
                color: #A5B4FC;
                border: 1px solid rgba(99, 102, 241, 0.35);
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {Styles.PRIMARY};
                color: #FFFFFF;
                border-color: {Styles.PRIMARY};
            }}
        """)
        self.btn_jump.clicked.connect(
            lambda: self.jump_clicked.emit(self.edited_item.start_ms)
        )
        meta_layout.addWidget(self.btn_jump)

        layout.addLayout(meta_layout)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)

        left_col = QVBoxLayout()
        left_col.setSpacing(3)
        self.lbl_orig_tag = QLabel(t("preview.tag_orig"))
        self.lbl_orig_tag.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {Styles.TEXT_FAINT}; letter-spacing: 0.5px;"
        )
        left_col.addWidget(self.lbl_orig_tag)

        orig_txt = self.original_item.text if self.original_item else ""
        self.lbl_orig = QLabel(orig_txt)
        self.lbl_orig.setWordWrap(True)
        self.lbl_orig.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_orig.setStyleSheet(f"""
            QLabel {{
                background: {Styles.SURFACE_DEEP};
                border: 1px solid {Styles.SURFACE_RAISED};
                border-radius: 6px;
                padding: 6px 8px;
                color: {Styles.TEXT_MUTED};
                font-size: 13px;
                line-height: 1.4;
            }}
        """)
        left_col.addWidget(self.lbl_orig, stretch=1)
        body_layout.addLayout(left_col, stretch=1)

        right_col = QVBoxLayout()
        right_col.setSpacing(3)
        self.lbl_edit_tag = QLabel(t("preview.tag_edit"))
        self.lbl_edit_tag.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {Styles.SUCCESS}; letter-spacing: 0.5px;"
        )
        right_col.addWidget(self.lbl_edit_tag)

        self.edit_text = QPlainTextEdit()
        self.edit_text.setPlainText(self.edited_item.text)
        self.edit_text.setTabChangesFocus(True)
        line_count = max(1, self.edited_item.text.count("\n") + 1)
        self.edit_text.setFixedHeight(max(40, min(140, line_count * 22 + 18)))
        self.edit_text.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #080D1A;
                border: 1px solid {Styles.BORDER};
                border-radius: 6px;
                color: {Styles.TEXT};
                font-size: 13px;
                padding: 5px 7px;
            }}
            QPlainTextEdit:focus {{
                border-color: {Styles.ACCENT};
                background: #0E1528;
            }}
        """)
        self.edit_text.textChanged.connect(self._on_text_changed)
        right_col.addWidget(self.edit_text, stretch=1)
        body_layout.addLayout(right_col, stretch=1)

        layout.addLayout(body_layout)

    def _on_text_changed(self):
        new_text = self.edit_text.toPlainText()
        self.edited_item.text = new_text
        line_count = max(1, new_text.count("\n") + 1)
        self.edit_text.setFixedHeight(max(40, min(140, line_count * 22 + 18)))
        self.text_changed.emit()

    def retranslate(self):
        self.btn_jump.setText(t("preview.btn_jump"))
        self.lbl_orig_tag.setText(t("preview.tag_orig"))
        self.lbl_edit_tag.setText(t("preview.tag_edit"))

    def matches_query(self, query: str) -> bool:
        if not query:
            return True
        q = query.lower()
        orig = self.original_item.text.lower() if self.original_item else ""
        edit = self.edited_item.text.lower()
        return q in orig or q in edit


class _CardSequence(Sequence):
    """Sequence view over diff cards that materializes a card when accessed.

    The viewer keeps one lightweight placeholder per cue and builds real
    ``SubtitleCard`` widgets only inside the viewport, so ``len()`` reports the
    cue count without paying widget cost. Indexing or iterating still returns
    real cards, which keeps tests, scripts and screenshot tooling working.
    """

    def __init__(self, viewer: "SubtitleDiffViewer") -> None:
        self._viewer = viewer

    def __len__(self) -> int:
        return self._viewer.cue_count

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [
                self._viewer.card_at(position)
                for position in range(*index.indices(len(self)))
            ]
        if not isinstance(index, int):
            raise TypeError("card indices must be integers or slices")
        if index < 0:
            index += len(self)
        return self._viewer.card_at(index)


#: Rows kept alive outside the viewport on each side, so a normal scroll does
#: not thrash widget creation while a drag across a long file still stays cheap.
_SCROLL_MARGIN_PX = 700


#: Placeholder height before a card exists, derived from the cue text; the real
#: card replaces it as soon as it is materialized.
def _placeholder_height(text: str) -> int:
    lines = max(1, text.count("\n") + 1)
    body = max(40, min(140, lines * 22 + 18))
    return 16 + 24 + 6 + body


class SubtitleDiffViewer(QWidget):
    cue_selected = pyqtSignal(int)
    subtitles_edited = pyqtSignal(list)
    count_changed = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_items: List[SubtitleItem] = []
        self.processed_items: List[SubtitleItem] = []
        #: Lazy sequence: ``len()`` is free, indexing materializes that card.
        self.cards: Sequence[SubtitleCard] = _CardSequence(self)
        self.active_card: Optional[SubtitleCard] = None
        # One row widget per cue: either a placeholder or a materialized card.
        self._rows: List[QWidget] = []
        self._live: dict = {}
        self._heights: List[int] = []
        self._hidden: List[bool] = []
        self._offsets: List[int] = [0]
        self._offsets_dirty = False
        self._original_by_index: dict = {}
        self._current_filter: str = ""
        self._active_position: Optional[int] = None
        #: ``_prefix_max_end[i]`` is the largest ``end_ms`` of cues ``0..i-1``
        #: (-1 for the first), bounding the fast path without assuming order.
        self._prefix_max_end: List[int] = []
        self._materializing = False

        self._setup_ui()

    @property
    def cue_count(self) -> int:
        """Number of cues currently loaded (materialized or not)."""
        return len(self.processed_items)

    @property
    def materialized_count(self) -> int:
        """Number of cards currently built; every other cue is a placeholder."""
        return len(self._live)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {Styles.SURFACE_RAISED};
                border-radius: 10px;
                background-color: #070B14;
            }}
        """)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        layout.addWidget(self.scroll_area)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def load_subtitles(
        self, original_items: List[SubtitleItem], processed_items: List[SubtitleItem]
    ):
        self.original_items = original_items or []
        self.processed_items = processed_items or []
        self.active_card = None
        self._active_position = None
        self._prefix_max_end = []
        self._original_by_index = {item.index: item for item in self.original_items}

        self.cards_container.setUpdatesEnabled(False)
        try:
            self._clear_rows()
            max_end_so_far = -1
            for idx, proc_item in enumerate(self.processed_items):
                placeholder = QWidget()
                placeholder.setFixedHeight(_placeholder_height(proc_item.text))
                self.cards_layout.insertWidget(idx, placeholder)
                hidden = bool(self._current_filter) and not self._matches(
                    idx, self._current_filter
                )
                placeholder.setVisible(not hidden)
                self._rows.append(placeholder)
                self._heights.append(placeholder.height())
                self._hidden.append(hidden)
                self._prefix_max_end.append(max_end_so_far)
                max_end_so_far = max(max_end_so_far, proc_item.end_ms)
            self._recompute_offsets()
        finally:
            self.cards_container.setUpdatesEnabled(True)

        # A new document starts at its first cue, not at the previous offset.
        self.scroll_area.verticalScrollBar().setValue(0)
        self._materialize_visible()
        visible = len(self._rows) - sum(self._hidden)
        self.count_changed.emit(visible, len(self._rows))

    def _clear_rows(self) -> None:
        self._live.clear()
        self.active_card = None
        while self.cards_layout.count() > 1:
            child = self.cards_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                # Reparent before deleteLater: the layout owns nothing and the
                # widget would stay visible until the event loop runs.
                widget.setParent(None)
                widget.deleteLater()
        self._rows = []
        self._heights = []
        self._hidden = []
        self._offsets = [0]

    def _original_for(self, position: int) -> SubtitleItem:
        processed = self.processed_items[position]
        original = self._original_by_index.get(processed.index)
        if original is None and position < len(self.original_items):
            original = self.original_items[position]
        return original if original is not None else processed

    def _matches(self, position: int, query: str) -> bool:
        needle = query.lower()
        edited = self.processed_items[position].text.lower()
        if needle in edited:
            return True
        return needle in self._original_for(position).text.lower()

    def card_at(self, position: int) -> SubtitleCard:
        """Return the card for ``position``, materializing it on demand."""
        if position < 0 or position >= len(self._rows):
            raise IndexError("card position out of range")
        live = self._live.get(position)
        if live is not None:
            return live

        card = SubtitleCard(
            self._original_for(position), self.processed_items[position]
        )
        card.jump_clicked.connect(self.cue_selected.emit)
        card.text_changed.connect(self._on_card_edited)
        self._swap_row(position, card)
        self._live[position] = card
        card.setVisible(not self._hidden[position])
        if self._active_position == position:
            self.active_card = card
            card.set_active(True)

        height = max(1, card.sizeHint().height())
        if abs(height - self._heights[position]) > 2:
            self._heights[position] = height
            self._offsets_dirty = True
        return card

    def _swap_row(self, position: int, widget: QWidget) -> None:
        old = self._rows[position]
        if self.active_card is old:
            self.active_card = None
        self.cards_layout.removeWidget(old)
        old.setParent(None)
        old.deleteLater()
        self.cards_layout.insertWidget(position, widget)
        self._rows[position] = widget

    def _recompute_offsets(self) -> None:
        offsets = [0] * (len(self._rows) + 1)
        cursor = self.cards_layout.contentsMargins().top()
        spacing = self.cards_layout.spacing()
        for position, height in enumerate(self._heights):
            offsets[position] = cursor
            if not self._hidden[position]:
                cursor += height + spacing
        offsets[len(self._rows)] = cursor
        self._offsets = offsets
        self._offsets_dirty = False

    def _on_scroll(self, _value: int) -> None:
        self._materialize_visible()

    def _materialize_visible(self) -> None:
        """Build the cards inside the viewport window and release the rest."""
        if self._materializing or not self._rows:
            return
        self._materializing = True
        try:
            viewport_height = self.scroll_area.viewport().height()
            if viewport_height <= 0:
                # Offscreen/not laid out yet: a plausible window beats none.
                viewport_height = 600
            scroll_top = self.scroll_area.verticalScrollBar().value()
            window_top = max(0, scroll_top - _SCROLL_MARGIN_PX)
            window_bottom = scroll_top + viewport_height + _SCROLL_MARGIN_PX
            start = max(0, bisect_right(self._offsets, window_top) - 1)
            end = min(len(self._rows), bisect_left(self._offsets, window_bottom))

            self._release_outside(start, end)
            for position in range(start, end):
                if self._hidden[position] or position in self._live:
                    continue
                self.card_at(position)
        finally:
            self._materializing = False
        if self._offsets_dirty:
            self._recompute_offsets()

    def _release_outside(self, start: int, end: int) -> None:
        for position, card in list(self._live.items()):
            if start - 1 <= position <= end:
                continue
            if card.hasFocus():
                # Never destroy the widget the user is typing in.
                continue
            self._live.pop(position, None)
            if self.active_card is card:
                self.active_card = None
            self._heights[position] = max(1, card.height() or self._heights[position])
            placeholder = QWidget()
            placeholder.setFixedHeight(self._heights[position])
            placeholder.setVisible(not self._hidden[position])
            self._swap_row(position, placeholder)
            self._offsets_dirty = True

    def _row_position(self, card: SubtitleCard) -> Optional[int]:
        for position, live in self._live.items():
            if live is card:
                return position
        return None

    def _on_card_edited(self):
        card = self.sender()
        if isinstance(card, SubtitleCard):
            position = self._row_position(card)
            if position is not None:
                # Height changes with the line count; keep the scroll length
                # and the virtual window in sync with the edited card.
                self._heights[position] = max(40, card.sizeHint().height())
                self._recompute_offsets()
        self.subtitles_edited.emit(self.processed_items)

    def get_processed_subtitles(self) -> List[SubtitleItem]:
        return self.processed_items

    def retranslate(self):
        for card in list(self._live.values()):
            card.retranslate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._materialize_visible()

    def highlight_cue_at_ms(self, pos_ms: int, auto_scroll: bool = True):
        """Highlight the cue under ``pos_ms``; first match in cue order wins.

        Playback calls this on every position tick, so it starts from the cue
        that is already active (A4): the common case is one comparison instead
        of a scan over every cue. When the position leaves that cue the full
        scan still decides, preserving the original first-match semantics.
        Only the active cue's card is materialized, so this stays O(1) in
        widget work even for files with thousands of cues (B5).
        """
        items = self.processed_items
        matching_position: Optional[int] = None
        cached_position = self._active_position
        if cached_position is not None and 0 <= cached_position < len(items):
            # The cached cue is the first match only when no earlier cue can
            # still be on screen; overlaps fall through to the full scan.
            earlier_end = self._prefix_max_end[cached_position]
            cached = items[cached_position]
            if earlier_end < pos_ms and cached.start_ms <= pos_ms <= cached.end_ms:
                matching_position = cached_position
        if matching_position is None:
            for position, item in enumerate(items):
                if item.start_ms <= pos_ms <= item.end_ms:
                    matching_position = position
                    break

        if matching_position == self._active_position:
            if matching_position is not None:
                self._refresh_active_card(matching_position)
                if auto_scroll:
                    self._ensure_visible(matching_position)
            return

        if self.active_card is not None:
            self.active_card.set_active(False)
        self._active_position = matching_position
        self.active_card = None
        if matching_position is None:
            return
        card = self.card_at(matching_position)
        self.active_card = card
        card.set_active(True)
        if auto_scroll:
            self._ensure_visible(matching_position)

    def _refresh_active_card(self, position: int) -> None:
        card = self.card_at(position)
        self.active_card = card
        card.set_active(True)

    def _ensure_visible(self, position: int) -> None:
        card = self.card_at(position)
        self.cards_layout.activate()
        self.scroll_area.ensureWidgetVisible(card, 0, 70)
        self._materialize_visible()

    def count_matches(self, query: str) -> tuple[int, int]:
        """Count cues matching ``query`` without touching their visibility.

        Searching must feel immediate even with thousands of cues, while the
        visibility pass is the expensive part (one layout invalidation per
        row). This lets the caller update the counter at keystroke time and
        defer the relayout.
        """
        query = (query or "").strip()
        total = len(self._rows)
        if not query:
            return total, total
        return sum(
            1 for position in range(total) if self._matches(position, query)
        ), total

    def filter_subtitles(self, query: str) -> tuple[int, int]:
        self._current_filter = (query or "").strip()
        applying = bool(self._current_filter)
        total_count = len(self._rows)

        self.cards_container.setUpdatesEnabled(False)
        try:
            for position in range(total_count):
                hidden = applying and not self._matches(position, self._current_filter)
                self._hidden[position] = hidden
                self._rows[position].setVisible(not hidden)
            self._recompute_offsets()
        finally:
            self.cards_container.setUpdatesEnabled(True)

        self._materialize_visible()
        visible_count = total_count - sum(self._hidden)
        self.count_changed.emit(visible_count, total_count)
        return visible_count, total_count


class VideoPreviewPlayer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "background-color: #070B14; border-radius: 12px; border: 1px solid #25304B;"
        )
        self.setMinimumHeight(180)
        self.setAcceptDrops(True)

        if (
            MULTIMEDIA_AVAILABLE
            and QMediaPlayer is not None
            and QAudioOutput is not None
        ):
            self.player = QMediaPlayer()
            self.audio_output = QAudioOutput(self)
            self.audio_output.setVolume(1.0)
            self.player.setAudioOutput(self.audio_output)
            self.player.tracksChanged.connect(self._on_tracks_changed)
            self.player.mediaStatusChanged.connect(self._on_media_status_changed)
            self.player.errorOccurred.connect(self._on_media_error)
        else:
            self.player = None
            self.audio_output = None
        self._media_error = False
        self._media_duration_ms = 0
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

        if MULTIMEDIA_AVAILABLE and QVideoWidget is not None:
            self.video_widget = QVideoWidget()
            if self.player is not None:
                self.player.setVideoOutput(self.video_widget)
            v_layout.addWidget(self.video_widget)
        else:
            self.video_widget = None

        self.sub_overlay = QLabel(t("preview.overlay_hint"), self.video_container)
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
        self.sub_overlay.mousePressEvent = lambda e: (
            self._browse_video()
            if (
                self.player is not None
                and (
                    not self.player.source().isValid() or self.player.source().isEmpty()
                )
            )
            else None
        )

        self.video_container.installEventFilter(self)
        if self.video_widget is not None:
            self.video_widget.installEventFilter(self)
        layout.addWidget(self.video_container)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(4, 0, 4, 0)
        ctrl_layout.setSpacing(10)

        self.play_btn = QPushButton()
        self.play_btn.setFixedSize(32, 32)
        self.play_btn.setEnabled(False)
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Styles.PRIMARY};
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {Styles.PRIMARY_HOVER}; }}
        """)
        self._sync_play_icon()

        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setAccessibleName(t("preview.seek_tooltip"))
        self.time_slider.setToolTip(t("preview.seek_tooltip"))
        self.time_slider.setEnabled(False)
        self.time_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 4px; background: {Styles.SURFACE_RAISED}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {Styles.PRIMARY}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: #FFFFFF; }}
        """)

        self.time_lbl = QLabel("00:00:00 / 00:00:00")
        self.time_lbl.setStyleSheet(
            f"color: {Styles.TEXT_MUTED}; font-size: 11px; font-family: monospace;"
        )

        self.btn_mute = QPushButton()
        self.btn_mute.setFixedSize(28, 28)
        self.btn_mute.setEnabled(False)
        self.btn_mute.setAccessibleName(t("preview.mute_tooltip"))
        self.btn_mute.setToolTip(t("preview.mute_tooltip"))
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
        self.vol_slider.setEnabled(False)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(70)
        self.vol_slider.setAccessibleName(t("preview.volume_tooltip"))
        self.vol_slider.setToolTip(t("preview.volume_tooltip"))
        self.vol_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 4px; background: {Styles.SURFACE_RAISED}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {Styles.SUCCESS}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ width: 10px; height: 10px; margin: -3px 0; border-radius: 5px; background: #FFFFFF; }}
        """)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        self._update_mute_icon(self.vol_slider.value())

        self.btn_load_video = QPushButton(t("preview.btn_load_video"))
        self.btn_load_video.setCursor(Qt.CursorShape.PointingHandCursor)
        # Accessible name set on creation: retranslate() is deferred, so set early to avoid unnamed controls.
        self.btn_load_video.setAccessibleName(t("preview.btn_load_video"))
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

    def retranslate(self):
        self.btn_load_video.setText(t("preview.btn_load_video"))
        self.btn_load_video.setAccessibleName(t("preview.btn_load_video"))
        self.sub_overlay.setText(t("preview.overlay_hint"))
        self.time_slider.setAccessibleName(t("preview.seek_tooltip"))
        self.time_slider.setToolTip(t("preview.seek_tooltip"))
        self.vol_slider.setAccessibleName(t("preview.volume_tooltip"))
        self.vol_slider.setToolTip(t("preview.volume_tooltip"))
        self._sync_play_icon()
        self._update_mute_icon(self.vol_slider.value())

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._sync_play_icon()
        if status in {
            QMediaPlayer.MediaStatus.NoMedia,
            QMediaPlayer.MediaStatus.InvalidMedia,
        }:
            self._media_error = status == QMediaPlayer.MediaStatus.InvalidMedia
            self._media_duration_ms = 0
            self._refresh_media_controls()
            self._sync_play_icon()
            if self._media_error:
                self._show_video_error()
            else:
                self._on_position_changed(self.player.position())

    def _on_media_error(self, _error, _error_string):
        self._media_error = True
        self._sync_play_icon()
        self._refresh_media_controls()
        self._show_video_error()

    def _show_video_error(self):
        self.sub_overlay.setText(t("preview.overlay_hint"))
        self._reposition_overlay()
        self.sub_overlay.show()
        self.sub_overlay.raise_()

    def _refresh_media_controls(self):
        if self.player is None:
            self.play_btn.setEnabled(False)
            self.time_slider.setEnabled(False)
            self.btn_mute.setEnabled(False)
            self.vol_slider.setEnabled(False)
            return
        source = self.player.source()
        has_source = source.isValid() and not source.isEmpty() and not self._media_error
        has_duration = self._media_duration_ms > 0
        self.play_btn.setEnabled(has_source)
        self.time_slider.setEnabled(has_source and has_duration)
        self.btn_mute.setEnabled(has_source)
        self.vol_slider.setEnabled(has_source)

    def _on_tracks_changed(self):
        if self.player is None:
            return
        if len(self.player.audioTracks()) > 0 and self.player.activeAudioTrack() == -1:
            self.player.setActiveAudioTrack(0)

    def _on_volume_changed(self, val: int):
        vol = val / 100.0
        if self.audio_output is not None:
            self.audio_output.setVolume(vol)
            # Adjusting volume implies intent to listen: unmute unless it is zero.
            if val > 0 and self.audio_output.isMuted():
                self.audio_output.setMuted(False)
            elif val == 0:
                self.audio_output.setMuted(True)
        self._update_mute_icon(val)

    def _toggle_mute(self):
        if not self.btn_mute.isEnabled() or self.audio_output is None:
            return
        is_muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not is_muted)
        if not is_muted:
            self._update_mute_icon(0)
        else:
            self._update_mute_icon(self.vol_slider.value())

    def _update_mute_icon(self, volume: int):
        muted = self.audio_output.isMuted() if self.audio_output is not None else False
        if muted or volume == 0:
            icon_name = "volume_mute"
            tip = t("preview.unmute_tooltip")
        elif volume < 50:
            icon_name = "volume_low"
            tip = t("preview.mute_tooltip")
        else:
            icon_name = "volume"
            tip = t("preview.mute_tooltip")
        self.btn_mute.setIcon(
            Icons.get_icon(
                icon_name,
                normal_color=Styles.TEXT_MUTED,
                active_color="#FFFFFF",
                size=16,
            )
        )
        self.btn_mute.setToolTip(tip)
        self.btn_mute.setAccessibleName(tip)

    def eventFilter(self, watched, event):
        if (
            watched in (self.video_container, self.video_widget)
            and event.type() == QEvent.Type.Resize
        ):
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
        path = ask_open_file(
            self, t("preview.select_video_title"), t("preview.video_filter")
        )
        if path:
            self.load_video(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext in [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".m4v"]:
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                ext = os.path.splitext(file_path)[1].lower()
                if ext in [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".m4v"]:
                    self.load_video(file_path)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    def _connect_signals(self):
        self.play_btn.clicked.connect(self._toggle_playback)
        if self.player is not None:
            self.player.playbackStateChanged.connect(self._sync_play_icon)
            self.player.positionChanged.connect(self._on_position_changed)
            self.player.durationChanged.connect(self._on_duration_changed)
        self.time_slider.sliderMoved.connect(self._set_position)

    def load_video(self, video_path: str):
        if not os.path.exists(video_path) or self.player is None:
            return
        self._media_error = False
        self._media_duration_ms = 0
        self.player.setSource(QUrl.fromLocalFile(video_path))
        self.sub_overlay.setText(t("preview.video_loaded"))
        self._reposition_overlay()
        self.sub_overlay.show()
        self.sub_overlay.raise_()
        self.time_slider.setRange(0, 0)
        self.time_slider.setValue(0)
        self._update_time_label(0, 0)
        self._refresh_media_controls()
        self._sync_play_icon()

    def set_subtitles(self, subtitles: List[SubtitleItem]):
        self.current_subtitles = subtitles
        if self.player is not None and self.player.position() > 0:
            self._on_position_changed(self.player.position())

    def seek_to_ms(self, ms: int):
        if not self.time_slider.isEnabled() or self.player is None:
            return
        was_playing = (
            QMediaPlayer is not None
            and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        self.player.setPosition(ms)
        self._on_position_changed(ms)
        if was_playing:
            self.player.play()

    def _sync_play_icon(self, _state=None):
        """Ensure play/pause icon reliably reflects playbackState (including EOS/error)."""
        playing = (
            self.player is not None
            and QMediaPlayer is not None
            and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        self.play_btn.setIcon(
            Icons.get_icon(
                "pause" if playing else "play",
                normal_color="#FFFFFF",
                active_color="#FFFFFF",
                size=16,
            )
        )
        tip = t("preview.pause_tooltip") if playing else t("preview.play_tooltip")
        self.play_btn.setToolTip(tip)
        self.play_btn.setAccessibleName(tip)

    def _toggle_playback(self):
        if not self.play_btn.isEnabled() or self.player is None:
            return
        if (
            QMediaPlayer is not None
            and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.player.pause()
        else:
            self.player.play()
        self._sync_play_icon()

    def _on_duration_changed(self, duration: int):
        self._media_duration_ms = max(0, duration)
        self.time_slider.setRange(0, self._media_duration_ms)
        pos = self.player.position() if self.player is not None else 0
        self._update_time_label(pos, self._media_duration_ms)
        self._refresh_media_controls()

    def _on_position_changed(self, pos: int):
        self._refresh_media_controls()
        if not self.time_slider.isSliderDown():
            self.time_slider.setValue(pos)
        self._update_time_label(pos, self._media_duration_ms)

        active_lines = []
        for item in self.current_subtitles:
            if item.start_ms <= pos <= item.end_ms:
                txt = item.text.strip()
                if txt and txt not in active_lines:
                    active_lines.append(txt)
        active_text = "\n".join(active_lines)

        if self._media_error:
            self._show_video_error()
        elif active_text:
            self.sub_overlay.setText(active_text)
            self._reposition_overlay()
            self.sub_overlay.show()
            self.sub_overlay.raise_()
        else:
            if (
                self.player is not None
                and self.player.source().isValid()
                and not self.player.source().isEmpty()
            ):
                self.sub_overlay.setText("")
                self.sub_overlay.hide()
            else:
                self.sub_overlay.setText(t("preview.overlay_hint"))
                self._reposition_overlay()
                self.sub_overlay.show()
                self.sub_overlay.raise_()

    def _set_position(self, pos: int):
        if self.time_slider.isEnabled() and self.player is not None:
            self.player.setPosition(pos)

    def _update_time_label(self, pos: int, dur: int):
        cur_str = self._format_ms(pos)
        dur_str = self._format_ms(dur)
        self.time_lbl.setText(f"{cur_str} / {dur_str}")

    def _format_ms(self, ms: int) -> str:
        s = (ms // 1000) % 60
        m = (ms // 60000) % 60
        h = ms // 3600000
        return f"{h:02d}:{m:02d}:{s:02d}"
