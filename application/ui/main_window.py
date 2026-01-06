# application/ui/main_window.py
import os
from queue import Queue
from threading import Thread
from typing import Optional

from PyQt6.QtCore import QTimer, pyqtSignal, QObject, Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QColor, QPalette
from PyQt6.QtWidgets import (
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QPushButton,
    QFileDialog,
    QCheckBox,
    QLineEdit,
    QComboBox,
    QProgressBar,
    QTextEdit,
    QMessageBox,
    QFrame,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)

from ..services.file_service import FileService
from ..services.subtitle_service import SubtitleService
from ..services.translation_service import TranslationService
from .styles import Styles
from .widgets import GlassCard, GlassButton, GlassInput


class ProgressSignal(QObject):
    progress_updated = pyqtSignal(str, object)


class GlassMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.input_file_path: Optional[str] = None
        self.output_directory: Optional[str] = None
        self.output_format: str = "srt"

        self.file_service = FileService()
        self.subtitle_service = SubtitleService()
        self.translation_service = TranslationService()

        self.progress_queue = Queue()
        self.timer = QTimer()
        self.progress_signal = ProgressSignal()

        self.progress_signal.progress_updated.connect(self.handle_progress_update)
        self.timer.timeout.connect(self.check_progress_queue)

        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("SRT4U - Subtitle Processor")
        self.resize(700, 600)
        self.setMinimumSize(600, 500)

        # Transparent window setup
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # self.setWindowFlags(Qt.WindowType.FramelessWindowHint) # Option for even cleaner look

        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        self.central_widget.setStyleSheet(Styles.MAIN_WINDOW)
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        self.main_layout.setSpacing(20)

        # Header
        header_layout = QVBoxLayout()
        self.title_label = QLabel("SRT4U")
        self.title_label.setStyleSheet(Styles.TITLE_LABEL)
        header_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("Professional Subtitle Processing & Translation")
        self.subtitle_label.setStyleSheet(Styles.SUBTITLE_LABEL)
        header_layout.addWidget(self.subtitle_label)

        self.main_layout.addLayout(header_layout)

        # File Selection Card
        file_card = GlassCard()
        file_card_layout = file_card.layout

        file_header = QHBoxLayout()
        file_header.addWidget(
            QLabel("1. Input & Output", styleSheet="color: white; font-weight: bold;")
        )
        file_card_layout.addLayout(file_header)

        # Input File Row
        input_row = QHBoxLayout()
        self.file_status = QLabel("No file selected")
        self.file_status.setStyleSheet("color: #CCC; font-size: 11px;")
        input_row.addWidget(self.file_status)
        input_row.addStretch()
        self.select_file_btn = GlassButton("Select File")
        self.select_file_btn.clicked.connect(self.handle_file_selection)
        input_row.addWidget(self.select_file_btn)
        file_card_layout.addLayout(input_row)

        # Output Dir Row
        out_row = QHBoxLayout()
        self.dir_status = QLabel("No directory selected")
        self.dir_status.setStyleSheet("color: #CCC; font-size: 11px;")
        out_row.addWidget(self.dir_status)
        out_row.addStretch()
        self.select_dir_btn = GlassButton("Select Output")
        self.select_dir_btn.clicked.connect(self.select_output_directory)
        out_row.addWidget(self.select_dir_btn)
        file_card_layout.addLayout(out_row)

        self.main_layout.addWidget(file_card)

        # Configuration Card
        config_card = GlassCard()
        config_layout = config_card.layout

        config_header = QLabel("2. Configuration")
        config_header.setStyleSheet("color: white; font-weight: bold;")
        config_layout.addWidget(config_header)

        # Translation row
        trans_row = QHBoxLayout()
        self.translation_toggle = QCheckBox("Enable Translation")
        self.translation_toggle.setStyleSheet(Styles.CHECKBOX_GLASS)
        trans_row.addWidget(self.translation_toggle)

        trans_row.addSpacing(20)
        trans_row.addWidget(QLabel("To Language:", styleSheet="color: #CCC;"))
        self.target_lang_input = GlassInput("e.g. es, fr, en")
        self.target_lang_input.setFixedWidth(100)
        trans_row.addWidget(self.target_lang_input)
        trans_row.addStretch()
        config_layout.addLayout(trans_row)

        # Format row
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Output Format:", styleSheet="color: #CCC;"))
        self.format_selector = QComboBox()
        self.format_selector.addItems(["srt", "vtt"])
        self.format_selector.setStyleSheet(Styles.COMBO_GLASS)
        self.format_selector.currentTextChanged.connect(self.update_output_format)
        format_row.addWidget(self.format_selector)
        format_row.addStretch()
        config_layout.addLayout(format_row)

        self.main_layout.addWidget(config_card)

        # Progress Area
        self.progress_area = QWidget()
        progress_layout = QVBoxLayout(self.progress_area)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(Styles.PROGRESS_GLASS)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(12)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #00E5FF; font-size: 11px;")
        progress_layout.addWidget(self.status_label)

        self.main_layout.addWidget(self.progress_area)

        # Action Button
        self.process_btn = GlassButton("START PROCESSING", primary=True)
        self.process_btn.setFixedHeight(50)
        self.process_btn.clicked.connect(self.process_subtitle_file)
        self.main_layout.addWidget(self.process_btn)

        # Footer Result
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.result_label)

        self.main_layout.addStretch()

    def handle_file_selection(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select subtitle file",
            "",
            "Subtitle files (*.srt *.vtt *.txt);;All files (*.*)",
        )
        if file_path:
            self.input_file_path = file_path
            self.file_status.setText(f"File: {os.path.basename(file_path)}")
        else:
            self.file_status.setText("No file selected")

    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select output directory", ""
        )
        if directory:
            self.output_directory = directory
            self.dir_status.setText(f"Dir: {os.path.basename(directory)}")

    def update_output_format(self, value: str):
        self.output_format = value

    def process_subtitle_file(self):
        if not self.input_file_path:
            self.show_message("Error", "Please select an input file", "warning")
            return
        if not self.output_directory:
            self.show_message("Error", "Please select an output directory", "warning")
            return
        if (
            self.translation_toggle.isChecked()
            and not self.target_lang_input.text().strip()
        ):
            self.show_message("Error", "Please enter a target language", "warning")
            return

        self.process_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Preparing...")
        self.result_label.setText("")

        worker = Thread(target=self._run_processing, args=(self.progress_queue,))
        worker.start()
        self.timer.start(100)

    def _run_processing(self, queue: Queue):
        try:
            processed_text = self.subtitle_service.process_subtitles(
                self.input_file_path,
                self.translation_toggle.isChecked(),
                self.target_lang_input.text().strip()
                if self.translation_toggle.isChecked()
                else None,
                lambda t, d: queue.put((t, d)),
            )
            queue.put(("success", processed_text))
        except Exception as e:
            queue.put(("error", str(e)))

    def check_progress_queue(self):
        try:
            while True:
                msg_type, data = self.progress_queue.get_nowait()
                self.progress_signal.progress_updated.emit(msg_type, data)
        except:
            pass

    def handle_progress_update(self, msg_type: str, data):
        if msg_type == "progress":
            self.progress_bar.setValue(int(data * 100))
        elif msg_type in ["status", "info"]:
            self.status_label.setText(str(data))
        elif msg_type == "success":
            self.timer.stop()
            self._finalize_success(data)
        elif msg_type == "error":
            self.timer.stop()
            self._finalize_error(data)

    def _finalize_success(self, content: str):
        try:
            base_name = os.path.basename(self.input_file_path)
            name_without_ext = os.path.splitext(base_name)[0]
            output_filename = f"{name_without_ext}_processed.{self.output_format}"
            output_path = os.path.join(self.output_directory, output_filename)

            if self.output_format == "vtt":
                content = f"WEBVTT\n\n{content}"

            with open(output_path, "w", encoding="UTF-8") as f:
                f.write(content)

            self.status_label.setText("Success!")
            self.result_label.setText(f"File saved to: {output_path}")
            self.result_label.setStyleSheet(
                f"color: {Styles.ACCENT_POSITIVE}; font-size: 11px;"
            )
        except Exception as e:
            self._finalize_error(str(e))
        finally:
            self.process_btn.setEnabled(True)
            QTimer.singleShot(5000, lambda: self.progress_bar.setVisible(False))

    def _finalize_error(self, message: str):
        self.status_label.setText("Failed")
        self.result_label.setText(f"Error: {message}")
        self.result_label.setStyleSheet(
            f"color: {Styles.ACCENT_NEGATIVE}; font-size: 11px;"
        )
        self.process_btn.setEnabled(True)

    def show_message(self, title, message, mode="info"):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        if mode == "warning":
            msg.setIcon(QMessageBox.Icon.Warning)
        elif mode == "error":
            msg.setIcon(QMessageBox.Icon.Critical)
        else:
            msg.setIcon(QMessageBox.Icon.Information)
        msg.exec()
