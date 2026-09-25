# application/ui/widgets.py
"""
Componentes visuales Glassmorphism según el mockup de SRT4U con alto contraste y diseño responsivo.
"""
import os
import math
from typing import Optional, List
from PyQt6.QtCore import Qt, QRect, QRectF, QSize, pyqtSignal, QUrl, QPoint
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


class SubtitleDiffViewer(QWidget):
    cue_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.left_col = self._create_column("Original", highlight=False)
        self.right_col = self._create_column("Traducido y limpio", highlight=True)

        layout.addWidget(self.left_col)
        layout.addWidget(self.right_col)

    def _create_column(self, title: str, highlight: bool = False) -> QWidget:
        container = QFrame()
        container.setObjectName("CardContainer")
        col_layout = QVBoxLayout(container)
        col_layout.setContentsMargins(14, 14, 14, 14)
        col_layout.setSpacing(10)

        color_str = "#10B981" if highlight else "#F8FAFC"
        header = QLabel(title)
        header.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {color_str};")
        col_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content_layout.addStretch()

        scroll.setWidget(content_widget)
        col_layout.addWidget(scroll)

        container.content_layout = content_layout
        container.content_widget = content_widget
        return container

    def load_subtitles(self, original_items: List[SubtitleItem], processed_items: List[SubtitleItem]):
        self._populate_column(self.left_col, original_items)
        self._populate_column(self.right_col, processed_items)

    def _populate_column(self, col_container: QWidget, items: List[SubtitleItem]):
        layout = col_container.content_layout
        while layout.count() > 1:
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for item in items:
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background: #1A2238;
                    border: 1px solid #2B3758;
                    border-radius: 8px;
                    padding: 8px;
                }
                QFrame:hover {
                    border-color: #6366F1;
                    background: #202A46;
                }
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(8, 8, 8, 8)
            c_layout.setSpacing(4)

            meta_layout = QHBoxLayout()
            idx_lbl = QLabel(f"#{item.index}")
            idx_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #818CF8;")
            time_lbl = QLabel(item.get_srt_time())
            time_lbl.setStyleSheet("font-size: 11px; font-family: monospace; color: #94A3B8;")
            meta_layout.addWidget(idx_lbl)
            meta_layout.addWidget(time_lbl)
            meta_layout.addStretch()

            text_lbl = QLabel(item.text)
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet("font-size: 13px; color: #F8FAFC;")

            c_layout.addLayout(meta_layout)
            c_layout.addWidget(text_lbl)

            start_time = item.start_ms
            card.mousePressEvent = lambda e, t=start_time: self.cue_selected.emit(t)
            layout.insertWidget(layout.count() - 1, card)


class VideoPreviewPlayer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #070B14; border-radius: 12px; border: 1px solid #25304B;")
        self.setFixedHeight(220)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
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

        self.sub_overlay = QLabel("Carga un video para previsualizar sincronización", self.video_widget)
        self.sub_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_overlay.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.85);
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 700;
                padding: 6px 12px;
                border-radius: 6px;
            }
        """)
        self.sub_overlay.adjustSize()
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

        ctrl_layout.addWidget(self.play_btn)
        ctrl_layout.addWidget(self.time_slider)
        ctrl_layout.addWidget(self.time_lbl)
        layout.addLayout(ctrl_layout)

    def _connect_signals(self):
        self.play_btn.clicked.connect(self._toggle_playback)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.time_slider.sliderMoved.connect(self._set_position)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.video_widget.width()
        h = self.video_widget.height()
        lbl_w = min(w - 20, 440)
        self.sub_overlay.setGeometry((w - lbl_w) // 2, h - 38, lbl_w, 30)

    def load_video(self, video_path: str):
        if os.path.exists(video_path):
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.sub_overlay.setText("Video cargado - Listo para reproducir")

    def set_subtitles(self, subtitles: List[SubtitleItem]):
        self.current_subtitles = subtitles

    def seek_to_ms(self, ms: int):
        self.player.setPosition(ms)

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

        active_text = ""
        for item in self.current_subtitles:
            if item.start_ms <= pos <= item.end_ms:
                active_text = item.text.replace("\n", " ")
                break

        if active_text:
            self.sub_overlay.setText(active_text)
            self.sub_overlay.show()
        else:
            self.sub_overlay.setText("")

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
