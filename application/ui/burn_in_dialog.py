"""
Diálogos de configuración visual y progreso en tiempo real para la incrustación
de subtítulos en vídeo (Burn-In / Hardsub) con diseño Glassmorphism.
"""

import os
from typing import List
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QProgressBar,
    QFileDialog,
    QFrame,
    QMessageBox,
    QCheckBox,
)

from ..services.subtitle_service import SubtitleItem
from ..services.video_burner_service import BurnInOptions, BurnInWorker
from ..services.i18n_service import t
from ..platform_utils import open_path, reveal_path
from .icons import Icons
from .styles import Styles, sync_minimum_size


class BurnInDialog(QDialog):
    """
    Modal de configuración de opciones de quemado visual y selección de rutas.
    """

    burn_requested = pyqtSignal(str, str, list, BurnInOptions)

    def __init__(
        self,
        video_path: str,
        subtitle_items: List[SubtitleItem],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(t("burn.dialog_title"))
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Styles.SURFACE_DEEP};
                color: {Styles.TEXT};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }}
            QLabel {{
                color: {Styles.TEXT_SUBTLE};
                font-size: 12px;
            }}
        """)

        self.video_path = video_path or ""
        self.subtitle_items = subtitle_items or []
        self._setup_ui()
        sync_minimum_size(self, QSize(620, 570))
        self.resize(self.minimumSize())
        self._update_preview()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(16)

        # 1. Header
        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel(t("burn.dialog_title"))
        title.setStyleSheet(f"font-size: 19px; font-weight: 800; color: {Styles.TEXT};")
        sub = QLabel(t("preview.subtitle"))
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size: 12px; color: {Styles.TEXT_MUTED};")
        header.addWidget(title)
        header.addWidget(sub)
        layout.addLayout(header)

        # 2. File Selection Card
        file_card = QFrame()
        file_card.setObjectName("FileCard")
        file_card.setStyleSheet(f"""
            QFrame#FileCard {{
                background: {Styles.SURFACE_ALT};
                border: 1px solid {Styles.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        f_layout = QVBoxLayout(file_card)
        f_layout.setContentsMargins(12, 12, 12, 12)
        f_layout.setSpacing(10)

        # Video origen
        v_box = QVBoxLayout()
        v_box.setSpacing(4)
        lbl_v = QLabel(t("burn.lbl_video_source"))
        lbl_v.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {Styles.TEXT_MUTED};"
        )
        v_row = QHBoxLayout()
        self.txt_video = QLineEdit(self.video_path)
        self.txt_video.setPlaceholderText("...")
        self.txt_video.setStyleSheet(self._input_style())
        btn_browse_vid = QPushButton(t("burn.btn_browse"))
        btn_browse_vid.setStyleSheet(self._btn_secondary_style())
        btn_browse_vid.setIcon(
            Icons.get_icon(
                "folder",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=15,
            )
        )
        btn_browse_vid.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse_vid.clicked.connect(self._browse_video)
        v_row.addWidget(self.txt_video, stretch=1)
        v_row.addWidget(btn_browse_vid)
        v_box.addWidget(lbl_v)
        v_box.addLayout(v_row)
        f_layout.addLayout(v_box)

        # Vídeo destino
        o_box = QVBoxLayout()
        o_box.setSpacing(4)
        lbl_o = QLabel(t("burn.lbl_output_file"))
        lbl_o.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {Styles.TEXT_MUTED};"
        )
        o_row = QHBoxLayout()

        default_out = ""
        if self.video_path:
            base, ext = os.path.splitext(self.video_path)
            default_out = f"{base}_subtitulado.mp4"

        self.txt_output = QLineEdit(default_out)
        self.txt_output.setPlaceholderText("...")
        self.txt_output.setStyleSheet(self._input_style())
        btn_browse_out = QPushButton(t("burn.btn_browse"))
        btn_browse_out.setStyleSheet(self._btn_secondary_style())
        btn_browse_out.setIcon(
            Icons.get_icon(
                "folder",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=15,
            )
        )
        btn_browse_out.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse_out.clicked.connect(self._browse_output)
        o_row.addWidget(self.txt_output, stretch=1)
        o_row.addWidget(btn_browse_out)
        o_box.addWidget(lbl_o)
        o_box.addLayout(o_row)
        f_layout.addLayout(o_box)

        # Badge conteo de subtítulos
        self.lbl_sub_badge = QLabel(t("burn.sub_badge", count=len(self.subtitle_items)))
        self.lbl_sub_badge.setStyleSheet(f"""
            background: #1E1B4B;
            color: {Styles.ACCENT_LIGHT};
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 4px;
            border: 1px solid #3730A3;
        """)
        f_layout.addWidget(self.lbl_sub_badge, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(file_card)

        # 3. Visual Configuration Grid
        opt_card = QFrame()
        opt_card.setObjectName("OptCard")
        opt_card.setStyleSheet(f"""
            QFrame#OptCard {{
                background: {Styles.SURFACE_ALT};
                border: 1px solid {Styles.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        opt_layout = QGridLayout(opt_card)
        opt_layout.setContentsMargins(12, 12, 12, 12)
        opt_layout.setHorizontalSpacing(14)
        opt_layout.setVerticalSpacing(8)

        # Tamaño
        opt_layout.addWidget(QLabel(t("burn.lbl_font_size")), 0, 0)
        self.cb_size = QComboBox()
        self.cb_size.addItem(t("burn.size_small"), "small")
        self.cb_size.addItem(t("burn.size_medium"), "medium")
        self.cb_size.addItem(t("burn.size_large"), "large")
        self.cb_size.setCurrentIndex(1)
        self.cb_size.setStyleSheet(self._combo_style())
        self.cb_size.currentIndexChanged.connect(self._update_preview)
        opt_layout.addWidget(self.cb_size, 0, 1)

        # Color
        opt_layout.addWidget(QLabel(t("burn.lbl_font_color")), 0, 2)
        self.cb_color = QComboBox()
        self.cb_color.addItem(t("burn.color_white"), "white")
        self.cb_color.addItem(t("burn.color_yellow"), "yellow")
        self.cb_color.addItem(t("burn.color_cyan"), "cyan")
        self.cb_color.setCurrentIndex(0)
        self.cb_color.setStyleSheet(self._combo_style())
        self.cb_color.currentIndexChanged.connect(self._update_preview)
        opt_layout.addWidget(self.cb_color, 0, 3)

        # Fondo / Caja
        opt_layout.addWidget(QLabel(t("burn.lbl_bg_box")), 1, 0)
        self.cb_box = QComboBox()
        self.cb_box.addItem(t("burn.box_trans"), "semi")
        self.cb_box.addItem(t("burn.box_none"), "none")
        self.cb_box.addItem(t("burn.box_solid"), "solid")
        self.cb_box.setCurrentIndex(0)
        self.cb_box.setStyleSheet(self._combo_style())
        self.cb_box.currentIndexChanged.connect(self._update_preview)
        opt_layout.addWidget(self.cb_box, 1, 1)

        # Calidad
        opt_layout.addWidget(QLabel(t("burn.lbl_quality")), 1, 2)
        self.cb_quality = QComboBox()
        self.cb_quality.addItem(t("burn.quality_high"), "high")
        self.cb_quality.addItem(t("burn.quality_fast"), "fast")
        self.cb_quality.setCurrentIndex(0)
        self.cb_quality.setStyleSheet(self._combo_style())
        opt_layout.addWidget(self.cb_quality, 1, 3)

        # Sincronización / Corrección de tiempos
        self.chk_fix_overlaps = QCheckBox(t("burn.chk_fix_overlaps"))
        self.chk_fix_overlaps.setChecked(True)
        self.chk_fix_overlaps.setStyleSheet("""
            QCheckBox {
                color: #CBD5E1;
                font-size: 11px;
                font-weight: 500;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 4px;
                border: 1px solid #475569;
                background: #0F172A;
            }
            QCheckBox::indicator:checked {
                background: #8B5CF6;
                border-color: #A78BFA;
            }
        """)
        opt_layout.addWidget(self.chk_fix_overlaps, 2, 0, 1, 4)

        layout.addWidget(opt_card)

        # 4. Live Preview Area
        prev_container = QFrame()
        prev_container.setFixedHeight(75)
        prev_container.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {Styles.SURFACE_RAISED}, stop:1 {Styles.SURFACE});
                border: 1px solid {Styles.BORDER};
                border-radius: 8px;
            }}
        """)
        prev_layout = QVBoxLayout(prev_container)
        prev_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_preview_sub = QLabel(t("burn.preview_hint"))
        self.lbl_preview_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_sub.setWordWrap(True)
        prev_layout.addWidget(self.lbl_preview_sub)
        layout.addWidget(prev_container)

        layout.addStretch()

        # 5. Bottom Actions
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)
        btn_bar.addStretch()

        btn_cancel = QPushButton(t("burn.btn_cancel"))
        btn_cancel.setStyleSheet(self._btn_secondary_style())
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        self.btn_start = QPushButton(t("burn.btn_burn"))
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background-color: {Styles.ACCENT};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-weight: 700;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {Styles.ACCENT_HOVER};
            }}
        """)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self._on_start_clicked)

        btn_bar.addWidget(btn_cancel)
        btn_bar.addWidget(self.btn_start)
        layout.addLayout(btn_bar)

    def _update_preview(self):
        size_id = self.cb_size.currentData()
        font_px = 14 if size_id == "small" else (18 if size_id == "medium" else 22)

        color_id = self.cb_color.currentData()
        color_hex = (
            "#FFFFFF"
            if color_id == "white"
            else ("#FFE600" if color_id == "yellow" else "#00FFFF")
        )

        box_id = self.cb_box.currentData()
        if box_id == "semi":
            bg = "rgba(0, 0, 0, 0.65)"
            border = "none"
        elif box_id == "solid":
            bg = "#000000"
            border = "none"
        else:
            bg = "transparent"
            border = "none"

        self.lbl_preview_sub.setStyleSheet(f"""
            QLabel {{
                color: {color_hex};
                font-size: {font_px}px;
                font-weight: 700;
                background-color: {bg};
                padding: 4px 14px;
                border-radius: 4px;
                border: {border};
            }}
        """)

    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("burn.select_video_title"), "", t("preview.video_filter")
        )
        if path:
            self.txt_video.setText(path)
            self.video_path = path
            if not self.txt_output.text():
                base, ext = os.path.splitext(path)
                self.txt_output.setText(f"{base}_subtitulado.mp4")

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            t("burn.save_video_title"),
            self.txt_output.text() or "video_subtitulado.mp4",
            t("preview.video_filter"),
        )
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self.txt_output.setText(path)

    def _on_start_clicked(self):
        v_path = self.txt_video.text().strip()
        o_path = self.txt_output.text().strip()

        if not v_path or not os.path.exists(v_path):
            QMessageBox.warning(
                self, t("burn.err_video_title"), t("burn.err_video_desc")
            )
            return

        if not o_path:
            QMessageBox.warning(
                self, t("burn.err_output_title"), t("burn.err_output_desc")
            )
            return

        if os.path.abspath(v_path) == os.path.abspath(o_path):
            QMessageBox.warning(
                self, t("burn.err_same_path_title"), t("burn.err_same_path_desc")
            )
            return

        if not self.subtitle_items:
            QMessageBox.warning(
                self, t("burn.err_no_subs_title"), t("burn.err_no_subs_desc")
            )
            return

        opts = BurnInOptions(
            font_size=self.cb_size.currentData(),
            font_color=self.cb_color.currentData(),
            box_style=self.cb_box.currentData(),
            quality_preset=self.cb_quality.currentData(),
            fix_overlaps=self.chk_fix_overlaps.isChecked(),
        )

        self.accept()
        self.burn_requested.emit(v_path, o_path, self.subtitle_items, opts)

    def _input_style(self):
        return f"""
            QLineEdit {{
                background: {Styles.SURFACE_DEEP};
                border: 1px solid {Styles.BORDER};
                border-radius: 6px;
                color: {Styles.TEXT};
                padding: 6px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {Styles.ACCENT};
            }}
        """

    def _btn_secondary_style(self):
        return f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: {Styles.TEXT_SUBTLE};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(99, 102, 241, 0.25);
                border-color: {Styles.ACCENT_LIGHT};
                color: #FFFFFF;
            }}
        """

    def _combo_style(self):
        return f"""
            QComboBox {{
                background: {Styles.SURFACE_DEEP};
                border: 1px solid {Styles.BORDER};
                border-radius: 6px;
                color: {Styles.TEXT};
                padding: 4px 8px;
                font-size: 12px;
            }}
            QComboBox:focus {{
                border-color: {Styles.ACCENT};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Styles.SURFACE};
                color: {Styles.TEXT};
                selection-background-color: {Styles.ACCENT};
                selection-color: #FFFFFF;
                border: 1px solid {Styles.BORDER};
                border-radius: 6px;
                outline: none;
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item {{
                color: {Styles.TEXT};
                background-color: transparent;
                min-height: 24px;
                padding: 4px 8px;
            }}
            QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {{
                background-color: {Styles.ACCENT};
                color: #FFFFFF;
            }}
        """


class BurnInProgressModal(QDialog):
    """
    Modal de progreso en tiempo real durante el quemado de vídeo por FFmpeg.
    """

    def __init__(
        self,
        video_path: str,
        output_path: str,
        subtitle_items: List[SubtitleItem],
        options: BurnInOptions,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(t("burn.rendering_title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Styles.SURFACE};
                color: {Styles.TEXT};
                border: 1px solid {Styles.SURFACE_RAISED};
                border-radius: 12px;
            }}
        """)

        self.output_path = output_path

        self._setup_ui()
        sync_minimum_size(self, QSize(500, 240))
        self.resize(self.minimumSize())
        self._start_worker(video_path, output_path, subtitle_items, options)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.lbl_title = QLabel(t("burn.dialog_title"))
        self.lbl_title.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {Styles.TEXT};"
        )
        layout.addWidget(self.lbl_title)

        self.lbl_status = QLabel(t("burn.encoding_status"))
        self.lbl_status.setStyleSheet(f"font-size: 12px; color: {Styles.TEXT_MUTED};")
        layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Styles.SURFACE_RAISED};
                border: 1px solid {Styles.BORDER};
                border-radius: 8px;
                height: 18px;
                text-align: center;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 11px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Styles.PRIMARY}, stop:1 {Styles.ACCENT});
                border-radius: 7px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        # Info de velocidad y tiempo
        self.info_layout = QHBoxLayout()
        self.lbl_speed = QLabel(t("burn.speed", speed="--"))
        self.lbl_speed.setStyleSheet(
            f"font-size: 11px; color: {Styles.TEXT_FAINT}; font-family: monospace;"
        )
        self.lbl_eta = QLabel(t("burn.eta", eta="--:--"))
        self.lbl_eta.setStyleSheet(
            f"font-size: 11px; color: {Styles.TEXT_FAINT}; font-family: monospace;"
        )
        self.info_layout.addWidget(self.lbl_speed)
        self.info_layout.addStretch()
        self.info_layout.addWidget(self.lbl_eta)
        layout.addLayout(self.info_layout)

        layout.addStretch()

        # Botonera
        self.btn_box = QHBoxLayout()
        self.btn_box.setSpacing(10)
        self.btn_box.addStretch()

        self.btn_cancel = QPushButton(t("burn.btn_cancel"))
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: {Styles.SURFACE_RAISED};
                border: 1px solid {Styles.BORDER};
                color: {Styles.DANGER};
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(239, 68, 68, 0.15);
                border-color: {Styles.DANGER};
            }}
        """)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._cancel_task)
        self.btn_box.addWidget(self.btn_cancel)

        # Botones post-éxito
        self.btn_play = QPushButton(t("burn.btn_play"))
        self.btn_play.setStyleSheet(f"""
            QPushButton {{
                background: {Styles.SUCCESS};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background: #059669; }}
        """)
        self.btn_play.setIcon(
            Icons.get_icon(
                "play", normal_color="#FFFFFF", active_color="#FFFFFF", size=15
            )
        )
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.clicked.connect(self._open_video)
        self.btn_play.hide()

        self.btn_folder = QPushButton(t("burn.btn_folder"))
        self.btn_folder.setIcon(
            Icons.get_icon(
                "folder", normal_color="#F8FAFC", active_color="#FFFFFF", size=15
            )
        )
        self.btn_folder.setStyleSheet(f"""
            QPushButton {{
                background: {Styles.SURFACE_RAISED};
                border: 1px solid {Styles.BORDER};
                color: {Styles.TEXT};
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {Styles.BORDER}; }}
        """)
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.clicked.connect(self._open_folder)
        self.btn_folder.hide()

        self.btn_close = QPushButton(t("burn.btn_close"))
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background: {Styles.ACCENT};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background: {Styles.ACCENT_HOVER}; }}
        """)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        self.btn_close.hide()

        self.btn_box.addWidget(self.btn_play)
        self.btn_box.addWidget(self.btn_folder)
        self.btn_box.addWidget(self.btn_close)
        layout.addLayout(self.btn_box)

    def _start_worker(
        self,
        video_path: str,
        output_path: str,
        subtitle_items: List[SubtitleItem],
        options: BurnInOptions,
    ):
        self.worker = BurnInWorker(
            video_path, output_path, subtitle_items, options, parent=self
        )
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.finished_success.connect(self._on_success)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.start()

    def _on_progress(self, percent: float, speed_str: str, eta_str: str):
        self.progress_bar.setValue(int(percent))
        self.lbl_speed.setText(t("burn.speed", speed=speed_str))
        self.lbl_eta.setText(t("burn.eta", eta=eta_str))

    def _on_success(self, output_path: str):
        self.progress_bar.setValue(100)
        self.lbl_title.setText(t("alert.burn_success_title"))
        self.lbl_title.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {Styles.SUCCESS};"
        )
        self.lbl_status.setText(
            t("alert.burn_success_desc", path=os.path.basename(output_path))
        )
        self.lbl_speed.hide()
        self.lbl_eta.hide()

        self.btn_cancel.hide()
        self.btn_play.show()
        self.btn_folder.show()
        self.btn_close.show()

    def _on_failed(self, error_msg: str):
        self.lbl_title.setText(t("burn.err_title"))
        self.lbl_title.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {Styles.DANGER};"
        )
        self.lbl_status.setText(t("burn.err_desc"))
        self.btn_cancel.setText(t("burn.btn_close"))
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.reject)
        QMessageBox.critical(self, t("burn.error_dialog_title"), error_msg)

    def _on_cancelled(self):
        self.lbl_title.setText(t("burn.cancelled_title"))
        self.lbl_status.setText(t("burn.cancelled_desc"))
        self.btn_cancel.setText(t("burn.btn_close"))
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.reject)

    def _cancel_task(self):
        self.lbl_status.setText(t("burn.stopping"))
        self.btn_cancel.setEnabled(False)
        self.worker.cancel()

    def _open_video(self):
        if os.path.exists(self.output_path):
            open_path(self.output_path)

    def _open_folder(self):
        if os.path.exists(self.output_path):
            reveal_path(self.output_path)
