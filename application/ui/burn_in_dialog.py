# application/ui/burn_in_dialog.py
"""
Diálogos de configuración visual y progreso en tiempo real para la incrustación
de subtítulos en vídeo (Burn-In / Hardsub) con diseño Glassmorphism.
"""
import os
import sys
import subprocess
from typing import List, Optional
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
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
)

from ..services.subtitle_service import SubtitleItem
from ..services.video_burner_service import BurnInOptions, BurnInWorker, VideoBurnerService


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
        self.setWindowTitle("Incrustar subtítulos en vídeo (Burn-In)")
        self.setFixedSize(620, 570)
        self.setStyleSheet("""
            QDialog {
                background-color: #0B0F19;
                color: #F8FAFC;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QLabel {
                color: #E2E8F0;
                font-size: 12px;
            }
        """)

        self.video_path = video_path or ""
        self.subtitle_items = subtitle_items or []
        self._setup_ui()
        self._update_preview()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(16)

        # 1. Header
        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("🔥 Incrustar subtítulos en vídeo")
        title.setStyleSheet("font-size: 19px; font-weight: 800; color: #F8FAFC;")
        sub = QLabel("Genera un nuevo archivo MP4 con los subtítulos integrados permanentemente.")
        sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        header.addWidget(title)
        header.addWidget(sub)
        layout.addLayout(header)

        # 2. File Selection Card
        file_card = QFrame()
        file_card.setObjectName("FileCard")
        file_card.setStyleSheet("""
            QFrame#FileCard {
                background: #111827;
                border: 1px solid #1F2937;
                border-radius: 8px;
            }
        """)
        f_layout = QVBoxLayout(file_card)
        f_layout.setContentsMargins(12, 12, 12, 12)
        f_layout.setSpacing(10)

        # Video origen
        v_box = QVBoxLayout()
        v_box.setSpacing(4)
        lbl_v = QLabel("Vídeo fuente original:")
        lbl_v.setStyleSheet("font-size: 11px; font-weight: 700; color: #94A3B8;")
        v_row = QHBoxLayout()
        self.txt_video = QLineEdit(self.video_path)
        self.txt_video.setPlaceholderText("Selecciona el archivo de vídeo...")
        self.txt_video.setStyleSheet(self._input_style())
        btn_browse_vid = QPushButton("📁 Cambiar vídeo...")
        btn_browse_vid.setStyleSheet(self._btn_secondary_style())
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
        lbl_o = QLabel("Archivo de salida resultante (.mp4):")
        lbl_o.setStyleSheet("font-size: 11px; font-weight: 700; color: #94A3B8;")
        o_row = QHBoxLayout()

        default_out = ""
        if self.video_path:
            base, ext = os.path.splitext(self.video_path)
            default_out = f"{base}_subtitulado.mp4"

        self.txt_output = QLineEdit(default_out)
        self.txt_output.setPlaceholderText("Ruta del vídeo de salida...")
        self.txt_output.setStyleSheet(self._input_style())
        btn_browse_out = QPushButton("📁 Examinar...")
        btn_browse_out.setStyleSheet(self._btn_secondary_style())
        btn_browse_out.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse_out.clicked.connect(self._browse_output)
        o_row.addWidget(self.txt_output, stretch=1)
        o_row.addWidget(btn_browse_out)
        o_box.addWidget(lbl_o)
        o_box.addLayout(o_row)
        f_layout.addLayout(o_box)

        # Badge conteo de subtítulos
        self.lbl_sub_badge = QLabel(f"Subtítulos listos: {len(self.subtitle_items)} líneas")
        self.lbl_sub_badge.setStyleSheet("""
            background: #1E1B4B;
            color: #A78BFA;
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
        opt_card.setStyleSheet("""
            QFrame#OptCard {
                background: #111827;
                border: 1px solid #1F2937;
                border-radius: 8px;
            }
        """)
        opt_layout = QGridLayout(opt_card)
        opt_layout.setContentsMargins(12, 12, 12, 12)
        opt_layout.setHorizontalSpacing(14)
        opt_layout.setVerticalSpacing(8)

        # Tamaño
        opt_layout.addWidget(QLabel("Tamaño de texto:"), 0, 0)
        self.cb_size = QComboBox()
        self.cb_size.addItems(["Pequeño", "Mediano", "Grande"])
        self.cb_size.setCurrentText("Mediano")
        self.cb_size.setStyleSheet(self._combo_style())
        self.cb_size.currentTextChanged.connect(self._update_preview)
        opt_layout.addWidget(self.cb_size, 0, 1)

        # Color
        opt_layout.addWidget(QLabel("Color de subtítulo:"), 0, 2)
        self.cb_color = QComboBox()
        self.cb_color.addItems(["Blanco", "Amarillo", "Cian"])
        self.cb_color.setCurrentText("Blanco")
        self.cb_color.setStyleSheet(self._combo_style())
        self.cb_color.currentTextChanged.connect(self._update_preview)
        opt_layout.addWidget(self.cb_color, 0, 3)

        # Fondo / Caja
        opt_layout.addWidget(QLabel("Fondo de lectura:"), 1, 0)
        self.cb_box = QComboBox()
        self.cb_box.addItems(["Caja semitransparente", "Sin fondo", "Caja sólida"])
        self.cb_box.setCurrentText("Caja semitransparente")
        self.cb_box.setStyleSheet(self._combo_style())
        self.cb_box.currentTextChanged.connect(self._update_preview)
        opt_layout.addWidget(self.cb_box, 1, 1)

        # Calidad
        opt_layout.addWidget(QLabel("Calidad / Velocidad:"), 1, 2)
        self.cb_quality = QComboBox()
        self.cb_quality.addItems(["Alta calidad", "Rápido"])
        self.cb_quality.setCurrentText("Alta calidad")
        self.cb_quality.setStyleSheet(self._combo_style())
        opt_layout.addWidget(self.cb_quality, 1, 3)

        layout.addWidget(opt_card)

        # 4. Live Preview Area
        prev_container = QFrame()
        prev_container.setFixedHeight(75)
        prev_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E293B, stop:1 #0F172A);
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)
        prev_layout = QVBoxLayout(prev_container)
        prev_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_preview_sub = QLabel("Así se verá el subtítulo incrustado en el vídeo")
        self.lbl_preview_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prev_layout.addWidget(self.lbl_preview_sub)
        layout.addWidget(prev_container)

        layout.addStretch()

        # 5. Bottom Actions
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)
        btn_bar.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(self._btn_secondary_style())
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        self.btn_start = QPushButton("🔥 Iniciar incrustación")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #8B5CF6;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #7C3AED;
            }
        """)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self._on_start_clicked)

        btn_bar.addWidget(btn_cancel)
        btn_bar.addWidget(self.btn_start)
        layout.addLayout(btn_bar)

    def _update_preview(self):
        size_txt = self.cb_size.currentText()
        font_px = 14 if size_txt == "Pequeño" else (18 if size_txt == "Mediano" else 22)

        color_txt = self.cb_color.currentText()
        color_hex = "#FFFFFF" if color_txt == "Blanco" else ("#FFE600" if color_txt == "Amarillo" else "#00FFFF")

        box_txt = self.cb_box.currentText()
        if box_txt == "Caja semitransparente":
            bg = "rgba(0, 0, 0, 0.65)"
            border = "none"
        elif box_txt == "Caja sólida":
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
            self,
            "Seleccionar vídeo original",
            "",
            "Archivos de vídeo (*.mp4 *.mkv *.webm *.avi *.mov *.flv *.m4v);;Todos los archivos (*.*)"
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
            "Guardar vídeo con subtítulos",
            self.txt_output.text() or "video_subtitulado.mp4",
            "Vídeo MP4 (*.mp4);;Todos los archivos (*.*)"
        )
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self.txt_output.setText(path)

    def _on_start_clicked(self):
        v_path = self.txt_video.text().strip()
        o_path = self.txt_output.text().strip()

        if not v_path or not os.path.exists(v_path):
            QMessageBox.warning(self, "Vídeo requerido", "Por favor, selecciona un archivo de vídeo existente.")
            return

        if not o_path:
            QMessageBox.warning(self, "Ruta requerida", "Por favor, especifica el nombre del vídeo de salida.")
            return

        if os.path.abspath(v_path) == os.path.abspath(o_path):
            QMessageBox.warning(
                self,
                "Ruta inválida",
                "El vídeo de salida no puede ser idéntico al vídeo original.\n"
                "Por favor, elige un nombre de archivo o carpeta diferente."
            )
            return

        if not self.subtitle_items:
            QMessageBox.warning(self, "Sin subtítulos", "No hay subtítulos disponibles para incrustar.")
            return

        opts = BurnInOptions(
            font_size=self.cb_size.currentText(),
            font_color=self.cb_color.currentText(),
            box_style=self.cb_box.currentText(),
            quality_preset=self.cb_quality.currentText(),
        )

        self.accept()
        self.burn_requested.emit(v_path, o_path, self.subtitle_items, opts)

    def _input_style(self):
        return """
            QLineEdit {
                background: #0B0F19;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #F8FAFC;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #8B5CF6;
            }
        """

    def _btn_secondary_style(self):
        return """
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: #E2E8F0;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(99, 102, 241, 0.25);
                border-color: #818CF8;
                color: #FFFFFF;
            }
        """

    def _combo_style(self):
        return """
            QComboBox {
                background: #0B0F19;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #F8FAFC;
                padding: 4px 8px;
                font-size: 12px;
            }
            QComboBox:focus {
                border-color: #8B5CF6;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #0F172A;
                color: #F8FAFC;
                selection-background-color: #8B5CF6;
                selection-color: #FFFFFF;
                border: 1px solid #334155;
                border-radius: 6px;
                outline: none;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                color: #F8FAFC;
                background-color: transparent;
                min-height: 24px;
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {
                background-color: #8B5CF6;
                color: #FFFFFF;
            }
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
        self.setWindowTitle("Renderizando subtítulos...")
        self.setFixedSize(500, 240)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #1E293B;
                border-radius: 12px;
            }
        """)

        self.output_path = output_path
        self._is_completed = False

        self._setup_ui()
        self._start_worker(video_path, output_path, subtitle_items, options)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.lbl_title = QLabel("🔥 Incrustando subtítulos en vídeo...")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #F8FAFC;")
        layout.addWidget(self.lbl_title)

        self.lbl_status = QLabel("Codificando vídeo con FFmpeg...")
        self.lbl_status.setStyleSheet("font-size: 12px; color: #94A3B8;")
        layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
                height: 18px;
                text-align: center;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #8B5CF6);
                border-radius: 7px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Info de velocidad y tiempo
        self.info_layout = QHBoxLayout()
        self.lbl_speed = QLabel("Velocidad: --")
        self.lbl_speed.setStyleSheet("font-size: 11px; color: #64748B; font-family: monospace;")
        self.lbl_eta = QLabel("Tiempo restante: Calculando...")
        self.lbl_eta.setStyleSheet("font-size: 11px; color: #64748B; font-family: monospace;")
        self.info_layout.addWidget(self.lbl_speed)
        self.info_layout.addStretch()
        self.info_layout.addWidget(self.lbl_eta)
        layout.addLayout(self.info_layout)

        layout.addStretch()

        # Botonera
        self.btn_box = QHBoxLayout()
        self.btn_box.setSpacing(10)
        self.btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancelar proceso")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: #1E293B;
                border: 1px solid #334155;
                color: #EF4444;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.15);
                border-color: #EF4444;
            }
        """)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._cancel_task)
        self.btn_box.addWidget(self.btn_cancel)

        # Botones post-éxito
        self.btn_play = QPushButton("▶ Reproducir vídeo")
        self.btn_play.setStyleSheet("""
            QPushButton {
                background: #10B981;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover { background: #059669; }
        """)
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.clicked.connect(self._open_video)
        self.btn_play.hide()

        self.btn_folder = QPushButton("📁 Abrir carpeta")
        self.btn_folder.setStyleSheet("""
            QPushButton {
                background: #1E293B;
                border: 1px solid #334155;
                color: #F8FAFC;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: #334155; }
        """)
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.clicked.connect(self._open_folder)
        self.btn_folder.hide()

        self.btn_close = QPushButton("Cerrar")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: #8B5CF6;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover { background: #7C3AED; }
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
        self.worker = BurnInWorker(video_path, output_path, subtitle_items, options, parent=self)
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.finished_success.connect(self._on_success)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.start()

    def _on_progress(self, percent: float, speed_str: str, eta_str: str):
        self.progress_bar.setValue(int(percent))
        self.lbl_speed.setText(f"Velocidad: {speed_str}")
        self.lbl_eta.setText(f"Restante: {eta_str}")

    def _on_success(self, output_path: str):
        self._is_completed = True
        self.progress_bar.setValue(100)
        self.lbl_title.setText("✅ ¡Subtítulos incrustados con éxito!")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #10B981;")
        self.lbl_status.setText(f"Archivo generado:\n{os.path.basename(output_path)}")
        self.lbl_speed.hide()
        self.lbl_eta.hide()

        self.btn_cancel.hide()
        self.btn_play.show()
        self.btn_folder.show()
        self.btn_close.show()

    def _on_failed(self, error_msg: str):
        self.lbl_title.setText("❌ Error al incrustar subtítulos")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #EF4444;")
        self.lbl_status.setText("Se produjo un error durante el proceso de codificación.")
        self.btn_cancel.setText("Cerrar")
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.reject)
        QMessageBox.critical(self, "Error de quemado", error_msg)

    def _on_cancelled(self):
        self.lbl_title.setText("Proceso cancelado")
        self.lbl_status.setText("El quemado de vídeo ha sido cancelado por el usuario.")
        self.btn_cancel.setText("Cerrar")
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.reject)

    def _cancel_task(self):
        self.lbl_status.setText("Deteniendo proceso de FFmpeg...")
        self.btn_cancel.setEnabled(False)
        self.worker.cancel()

    def _open_video(self):
        if os.path.exists(self.output_path):
            if sys.platform == "win32":
                os.startfile(self.output_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.output_path])
            else:
                subprocess.Popen(["xdg-open", self.output_path])

    def _open_folder(self):
        if os.path.exists(self.output_path):
            folder = os.path.dirname(self.output_path)
            if sys.platform == "win32":
                subprocess.Popen(f'explorer /select,"{os.path.normpath(self.output_path)}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", self.output_path])
            else:
                subprocess.Popen(["xdg-open", folder])
