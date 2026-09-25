# application/ui/main_window.py
import os
import subprocess
import sys
import time
from typing import Optional, List

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QStackedWidget,
    QLabel,
    QPushButton,
    QComboBox,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QFrame,
    QScrollArea,
    QSplitter,
    QCheckBox,
)

from .styles import Styles
from .widgets import (
    ModernToggle,
    DropZone,
    OptionCard,
    MetricCard,
    SubtitleDiffViewer,
    VideoPreviewPlayer,
    ProgressModal,
    LogoBadge,
)
from .burn_in_dialog import BurnInDialog, BurnInProgressModal, BurnInOptions
from ..services.config_service import ConfigService
from ..services.subtitle_service import SubtitleService, ProcessingResult
from ..services.translation_service import TranslationService


class ProcessWorker(QThread):
    step_updated = pyqtSignal(str, object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        service: SubtitleService,
        file_path: str,
        do_clean: bool,
        do_translate: bool,
        target_lang: str,
        source_lang: str,
        engine: str,
        target_format: Optional[str] = None,
        parallel: bool = True,
    ):
        super().__init__()
        self.service = service
        self.file_path = file_path
        self.do_clean = do_clean
        self.do_translate = do_translate
        self.target_lang = target_lang
        self.source_lang = source_lang
        self.engine = engine
        self.target_format = target_format
        self.parallel = parallel

    def run(self):
        def callback(event_name: str, payload: object):
            self.step_updated.emit(event_name, payload)

        try:
            result = self.service.process_subtitles(
                file_path=self.file_path,
                do_clean=self.do_clean,
                do_translate=self.do_translate,
                target_language=self.target_lang,
                source_language=self.source_lang,
                engine=self.engine,
                target_format=self.target_format,
                parallel=self.parallel,
                progress_callback=callback,
            )
            self.completed.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SRT4U - Subtitle Processor")
        self.resize(1120, 780)
        self.setMinimumSize(920, 640)

        self.dark_mode = True
        self.config_service = ConfigService()
        self.translation_service = TranslationService(self.config_service)
        self.subtitle_service = SubtitleService(self.translation_service)

        self.current_subtitle_path: Optional[str] = None
        self.current_video_path: Optional[str] = None
        self.last_result: Optional[ProcessingResult] = None
        self.saved_output_path: Optional[str] = None

        self._setup_ui()
        self._load_config_values()
        self._apply_theme()

    def _setup_ui(self):
        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)

        root_layout = QHBoxLayout(self.central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Sidebar lateral
        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

        # 2. Main Content Stack
        self.stack = QStackedWidget()
        self.page_home = self._build_home_page()
        self.page_preview = self._build_preview_page()
        self.page_clean = self._build_clean_page()
        self.page_convert = self._build_convert_page()
        self.page_batch = self._build_batch_page()
        self.page_settings = self._build_settings_page()
        self.page_completed = self._build_completed_page()

        self.stack.addWidget(self.page_home)       # 0
        self.stack.addWidget(self.page_preview)    # 1
        self.stack.addWidget(self.page_clean)      # 2
        self.stack.addWidget(self.page_convert)    # 3
        self.stack.addWidget(self.page_batch)      # 4
        self.stack.addWidget(self.page_settings)   # 5
        self.stack.addWidget(self.page_completed)  # 6

        root_layout.addWidget(self.stack)
        self._switch_page(0)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(8)

        # Brand Header
        logo_layout = QHBoxLayout()
        logo_layout.setSpacing(12)
        logo_badge = LogoBadge()
        
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        app_title = QLabel("SRT4U")
        app_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #F8FAFC;")
        app_sub = QLabel("Subtitle Processor")
        app_sub.setStyleSheet("font-size: 11px; color: #818CF8; font-weight: 500;")
        title_box.addWidget(app_title)
        title_box.addWidget(app_sub)

        logo_layout.addWidget(logo_badge)
        logo_layout.addLayout(title_box)
        logo_layout.addStretch()

        layout.addLayout(logo_layout)
        layout.addSpacing(20)

        # Nav Buttons
        self.nav_buttons: List[QPushButton] = []
        nav_items = [
            ("🏠  Inicio", 0),
            ("🌐  Traducir", 1),
            ("✨  Limpiar", 2),
            ("🔄  Convertir", 3),
            ("📁  Procesamiento por lote", 4),
            ("⚙️  Configuración", 5),
        ]

        for text, page_idx in nav_items:
            btn = QPushButton(text)
            btn.setProperty("class", "nav-btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=page_idx: self._switch_page(idx))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)

        layout.addStretch()
        return sidebar

    def _switch_page(self, page_index: int):
        self.stack.setCurrentIndex(page_index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setProperty("active", "true" if i == page_index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self._apply_theme()

    def _apply_theme(self):
        self.central_widget.setStyleSheet(Styles.get_main_style(self.dark_mode))
        self.btn_theme.setText("☀️" if self.dark_mode else "🌙")

    # ------------------ PÁGINA: INICIO ------------------
    def _build_home_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        # Contenedor centrado para evitar estiramiento excesivo en tiling WMs (dwm)
        container = QWidget()
        container.setMaximumWidth(1020)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        # Header con Theme Toggle
        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(4)
        title = QLabel("Traducir subtítulos")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        subtitle = QLabel("Selecciona tu archivo, el idioma de destino y las opciones de procesamiento.")
        subtitle.setStyleSheet("font-size: 13px; color: #94A3B8;")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        self.btn_theme = QPushButton("☀️")
        self.btn_theme.setFixedSize(38, 38)
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.setStyleSheet("""
            QPushButton {
                background: #1E293B;
                border: 1px solid #334155;
                border-radius: 19px;
                font-size: 16px;
                color: #F8FAFC;
            }
            QPushButton:hover {
                background: #334155;
                border-color: #6366F1;
            }
        """)
        self.btn_theme.clicked.connect(self._toggle_theme)

        header_row.addLayout(header_text)
        header_row.addStretch()
        header_row.addWidget(self.btn_theme)
        layout.addLayout(header_row)

        # Drop Zone
        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.drop_zone)

        # Selector Row (3 columnas: Origen, Destino, Modelo)
        selector_card = QFrame()
        selector_card.setObjectName("CardContainer")
        sel_layout = QHBoxLayout(selector_card)
        sel_layout.setContentsMargins(18, 14, 18, 14)
        sel_layout.setSpacing(18)

        # 1. Idioma Origen
        src_box = QVBoxLayout()
        src_box.setSpacing(6)
        src_lbl = QLabel("Idioma de origen")
        src_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")
        self.cb_source_lang = QComboBox()
        self.cb_source_lang.addItem("Detectar automáticamente", "auto")
        for lang in self.translation_service.SUPPORTED_LANGUAGES:
            self.cb_source_lang.addItem(f"{lang['flag']} {lang['name']}", lang["code"])
        src_box.addWidget(src_lbl)
        src_box.addWidget(self.cb_source_lang)

        # 2. Idioma Destino
        tgt_box = QVBoxLayout()
        tgt_box.setSpacing(6)
        tgt_lbl = QLabel("Idioma de destino")
        tgt_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")
        self.cb_target_lang = QComboBox()
        for lang in self.translation_service.SUPPORTED_LANGUAGES:
            self.cb_target_lang.addItem(f"{lang['flag']} {lang['name']}", lang["code"])
        tgt_box.addWidget(tgt_lbl)
        tgt_box.addWidget(self.cb_target_lang)

        # 3. Modelo de Traducción
        engine_box = QVBoxLayout()
        engine_box.setSpacing(6)
        engine_lbl = QLabel("Modelo de traducción")
        engine_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")
        self.cb_engine = QComboBox()
        self.cb_engine.addItem("DeepL (recomendado)", "deepl")
        self.cb_engine.addItem("Google Translate", "google")
        self.cb_engine.addItem("OpenAI / LLM", "openai")
        engine_box.addWidget(engine_lbl)
        engine_box.addWidget(self.cb_engine)

        sel_layout.addLayout(src_box)
        sel_layout.addLayout(tgt_box)
        sel_layout.addLayout(engine_box)
        layout.addWidget(selector_card)

        # Cuadrícula 2x2 de Opciones (según mockup)
        grid_layout = QGridLayout()
        grid_layout.setSpacing(14)

        self.toggle_translate = ModernToggle(checked=True)
        self.toggle_preserve = ModernToggle(checked=True)
        self.toggle_clean = ModernToggle(checked=True)
        self.toggle_parallel = ModernToggle(checked=True)

        card_translate = OptionCard(
            "Traducir subtítulos",
            "Usa la API de traducción seleccionada.",
            self.toggle_translate
        )
        card_preserve = OptionCard(
            "Mantener formato original",
            "Conserva la sincronización y la estructura.",
            self.toggle_preserve
        )
        card_clean = OptionCard(
            "Limpiar subtítulos",
            "Elimina spam, URLs, IDs y contenido no deseado.",
            self.toggle_clean
        )
        card_parallel = OptionCard(
            "Procesamiento paralelo",
            "Traduce múltiples bloques simultáneamente.",
            self.toggle_parallel
        )

        grid_layout.addWidget(card_translate, 0, 0)
        grid_layout.addWidget(card_preserve, 0, 1)
        grid_layout.addWidget(card_clean, 1, 0)
        grid_layout.addWidget(card_parallel, 1, 1)
        layout.addLayout(grid_layout)

        # Botón de Acción Principal (🚀 Procesar archivo)
        self.btn_process = QPushButton("🚀 Procesar archivo")
        self.btn_process.setObjectName("PrimaryBtn")
        self.btn_process.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_process.setMinimumHeight(48)
        self.btn_process.clicked.connect(self._start_processing)
        layout.addWidget(self.btn_process)

        layout.addStretch()

        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    # ------------------ PÁGINA: VISTA PREVIA (STUDIO DE TRADUCCIÓN) ------------------
    def _build_preview_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(24, 18, 24, 18)
        page_layout.setSpacing(10)

        # 1. Top Header & Action Buttons
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(12)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        p_title = QLabel("🎬 Studio de Traducción")
        p_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #F8FAFC;")
        p_sub = QLabel("Previsualiza vídeo, edita subtítulos frase a frase y sincroniza en directo.")
        p_sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        header_text.addWidget(p_title)
        header_text.addWidget(p_sub)

        top_bar.addLayout(header_text)
        top_bar.addStretch()

        self.btn_open_orig = QPushButton("📁 Abrir subtítulo")
        self.btn_open_orig.setProperty("class", "secondary-btn")
        self.btn_open_orig.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_orig.clicked.connect(self._browse_preview_file)

        self.btn_export = QPushButton("💾 Guardar subtítulo")
        self.btn_export.setObjectName("PrimaryBtn")
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._export_result_file)

        self.btn_burn_in = QPushButton("🔥 Incrustar en vídeo")
        self.btn_burn_in.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_burn_in.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8B5CF6, stop:1 #EC4899);
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7C3AED, stop:1 #DB2777);
            }
        """)
        self.btn_burn_in.clicked.connect(self._open_burn_in_dialog)

        top_bar.addWidget(self.btn_open_orig)
        top_bar.addWidget(self.btn_export)
        top_bar.addWidget(self.btn_burn_in)
        page_layout.addLayout(top_bar)

        # 2. Control & Search Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet("""
            QFrame {
                background: #0F172A;
                border: 1px solid #1E293B;
                border-radius: 8px;
            }
        """)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(14)

        # Search bar
        self.preview_search_input = QLineEdit()
        self.preview_search_input.setPlaceholderText("🔍 Buscar por texto en original o traducción...")
        self.preview_search_input.setClearButtonEnabled(True)
        self.preview_search_input.setStyleSheet("""
            QLineEdit {
                background: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #F8FAFC;
                padding: 6px 12px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #8B5CF6;
                background: #1A2234;
            }
        """)
        self.preview_search_input.textChanged.connect(self._on_preview_search_changed)
        tb_layout.addWidget(self.preview_search_input, stretch=2)

        # Counter badge
        self.lbl_preview_sub_counter = QLabel("0 subtítulos")
        self.lbl_preview_sub_counter.setStyleSheet("""
            QLabel {
                background: #1E293B;
                color: #94A3B8;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #334155;
            }
        """)
        tb_layout.addWidget(self.lbl_preview_sub_counter)

        # Auto-scroll toggle
        self.chk_autoscroll = QCheckBox("Auto-scroll con vídeo")
        self.chk_autoscroll.setChecked(True)
        self.chk_autoscroll.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_autoscroll.setStyleSheet("""
            QCheckBox {
                color: #CBD5E1;
                font-size: 12px;
                font-weight: 600;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #475569;
                background: #1E293B;
            }
            QCheckBox::indicator:checked {
                background: #8B5CF6;
                border-color: #8B5CF6;
            }
        """)
        tb_layout.addWidget(self.chk_autoscroll)

        page_layout.addWidget(toolbar)

        # 3. Cinema Splitter (Video Player on TOP, Subtitle Diff Viewer on BOTTOM)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet("""
            QSplitter::handle:vertical {
                background-color: #1E293B;
                height: 6px;
                margin: 2px 20px;
                border-radius: 3px;
            }
            QSplitter::handle:vertical:hover {
                background-color: #8B5CF6;
            }
        """)

        self.video_player = VideoPreviewPlayer()
        self.diff_viewer = SubtitleDiffViewer()

        # Connect signals
        self.diff_viewer.subtitles_edited.connect(self._on_subtitles_edited)
        self.diff_viewer.cue_selected.connect(self.video_player.seek_to_ms)
        self.diff_viewer.count_changed.connect(self._on_preview_count_changed)
        self.video_player.player.positionChanged.connect(self._on_video_position_sync)

        splitter.addWidget(self.video_player)
        splitter.addWidget(self.diff_viewer)
        splitter.setSizes([260, 420])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setChildrenCollapsible(False)

        page_layout.addWidget(splitter, stretch=1)
        return page

    # ------------------ PÁGINA: LIMPIAR ------------------
    def _build_clean_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        container = QWidget()
        container.setMaximumWidth(1020)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        title = QLabel("Limpieza automática de subtítulos")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        subtitle = QLabel("Elimina spam, URLs, canales de Telegram y créditos sin alterar sincronización.")
        subtitle.setStyleSheet("font-size: 13px; color: #94A3B8;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.clean_drop_zone = DropZone()
        self.clean_drop_zone.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.clean_drop_zone)

        btn_fast_clean = QPushButton("✨ Limpiar contenido no deseado")
        btn_fast_clean.setObjectName("PrimaryBtn")
        btn_fast_clean.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fast_clean.setMinimumHeight(46)
        btn_fast_clean.clicked.connect(self._start_fast_clean)
        layout.addWidget(btn_fast_clean)

        layout.addStretch()
        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    # ------------------ PÁGINA: CONVERTIR ------------------
    def _build_convert_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        container = QWidget()
        container.setMaximumWidth(1020)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        title = QLabel("Convertir formatos de subtítulos")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        subtitle = QLabel("Convierte instantáneamente entre .srt, .ass, .vtt y .txt sin tocar tiempos.")
        subtitle.setStyleSheet("font-size: 13px; color: #94A3B8;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.convert_drop_zone = DropZone()
        self.convert_drop_zone.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.convert_drop_zone)

        conv_card = QFrame()
        conv_card.setObjectName("CardContainer")
        c_layout = QHBoxLayout(conv_card)
        c_layout.setContentsMargins(18, 14, 18, 14)
        c_lbl = QLabel("Formato de salida deseado:")
        c_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")
        c_layout.addWidget(c_lbl)

        self.cb_convert_format = QComboBox()
        self.cb_convert_format.addItems(["SRT (.srt)", "VTT (.vtt)", "ASS (.ass)", "TXT (.txt)"])
        c_layout.addWidget(self.cb_convert_format)
        c_layout.addStretch()
        layout.addWidget(conv_card)

        btn_run_convert = QPushButton("🔄 Convertir y guardar")
        btn_run_convert.setObjectName("PrimaryBtn")
        btn_run_convert.setMinimumHeight(46)
        btn_run_convert.clicked.connect(self._run_format_conversion)
        layout.addWidget(btn_run_convert)

        layout.addStretch()
        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    # ------------------ PÁGINA: PROCESAMIENTO POR LOTE ------------------
    def _build_batch_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        container = QWidget()
        container.setMaximumWidth(1020)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        title = QLabel("Procesamiento por lote")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        subtitle = QLabel("Traduce, limpia o convierte múltiples archivos en paralelo.")
        subtitle.setStyleSheet("font-size: 13px; color: #94A3B8;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        btn_layout = QHBoxLayout()
        self.btn_add_batch = QPushButton("➕ Añadir subtítulos")
        self.btn_add_batch.setProperty("class", "secondary-btn")
        self.btn_add_batch.clicked.connect(self._add_batch_files)

        self.btn_clear_batch = QPushButton("🗑️ Limpiar cola")
        self.btn_clear_batch.setProperty("class", "secondary-btn")
        self.btn_clear_batch.clicked.connect(self._clear_batch_table)

        btn_layout.addWidget(self.btn_add_batch)
        btn_layout.addWidget(self.btn_clear_batch)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.batch_table = QTableWidget()
        self.batch_table.setColumnCount(4)
        self.batch_table.setHorizontalHeaderLabels(["Archivo", "Tamaño", "Formato", "Estado"])
        self.batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.batch_table.setMinimumHeight(240)
        layout.addWidget(self.batch_table)

        self.btn_start_batch = QPushButton("▶ Procesar todos los archivos")
        self.btn_start_batch.setObjectName("PrimaryBtn")
        self.btn_start_batch.setMinimumHeight(46)
        self.btn_start_batch.clicked.connect(self._run_batch_processing)
        layout.addWidget(self.btn_start_batch)

        layout.addStretch()
        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    # ------------------ PÁGINA: CONFIGURACIÓN ------------------
    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        container = QWidget()
        container.setMaximumWidth(1020)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(18)

        title = QLabel("Configuración de servicios")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        layout.addWidget(title)

        # DeepL Card
        deepl_card = QFrame()
        deepl_card.setObjectName("CardContainer")
        d_layout = QVBoxLayout(deepl_card)
        d_layout.setContentsMargins(18, 16, 18, 16)
        d_layout.setSpacing(10)

        d_title = QLabel("DeepL API")
        d_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #F8FAFC;")
        d_desc = QLabel("Clave de API para traducciones de alta fidelidad.")
        d_desc.setStyleSheet("font-size: 12px; color: #94A3B8;")
        d_layout.addWidget(d_title)
        d_layout.addWidget(d_desc)

        self.txt_deepl_key = QLineEdit()
        self.txt_deepl_key.setPlaceholderText("Clave API de DeepL (ej. 12345678-abcd...)")
        d_layout.addWidget(self.txt_deepl_key)

        type_layout = QHBoxLayout()
        self.rb_deepl_free = QRadioButton("DeepL Free API")
        self.rb_deepl_pro = QRadioButton("DeepL Pro API")
        self.rb_deepl_free.setStyleSheet("color: #F8FAFC;")
        self.rb_deepl_pro.setStyleSheet("color: #F8FAFC;")
        self.rb_deepl_free.setChecked(True)
        self.bg_deepl = QButtonGroup()
        self.bg_deepl.addButton(self.rb_deepl_free)
        self.bg_deepl.addButton(self.rb_deepl_pro)
        type_layout.addWidget(self.rb_deepl_free)
        type_layout.addWidget(self.rb_deepl_pro)
        type_layout.addStretch()
        d_layout.addLayout(type_layout)

        layout.addWidget(deepl_card)

        # OpenAI / LLM Card
        openai_card = QFrame()
        openai_card.setObjectName("CardContainer")
        o_layout = QVBoxLayout(openai_card)
        o_layout.setContentsMargins(18, 16, 18, 16)
        o_layout.setSpacing(10)

        o_title = QLabel("OpenAI / Endpoint Compatible (Ollama, OpenRouter)")
        o_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #F8FAFC;")
        o_layout.addWidget(o_title)

        self.txt_openai_key = QLineEdit()
        self.txt_openai_key.setPlaceholderText("API Key (opcional para endpoints locales)")
        o_layout.addWidget(self.txt_openai_key)

        self.txt_openai_url = QLineEdit()
        self.txt_openai_url.setPlaceholderText("Base URL (ej. https://api.openai.com/v1 o http://localhost:11434/v1)")
        o_layout.addWidget(self.txt_openai_url)

        self.txt_openai_model = QLineEdit()
        self.txt_openai_model.setPlaceholderText("Modelo (ej. gpt-4o-mini)")
        o_layout.addWidget(self.txt_openai_model)

        layout.addWidget(openai_card)

        btn_save = QPushButton("💾 Guardar configuración")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.setMinimumHeight(46)
        btn_save.clicked.connect(self._save_settings)
        layout.addWidget(btn_save)

        layout.addStretch()
        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    # ------------------ PÁGINA: COMPLETADO ------------------
    def _build_completed_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        container = QWidget()
        container.setMaximumWidth(1020)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(22)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(14)
        check_icon = QLabel("✅")
        check_icon.setStyleSheet("font-size: 34px;")
        
        text_layout = QVBoxLayout()
        c_title = QLabel("Procesamiento completado")
        c_title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        c_sub = QLabel("El archivo se ha procesado y guardado correctamente.")
        c_sub.setStyleSheet("font-size: 13px; color: #94A3B8;")
        text_layout.addWidget(c_title)
        text_layout.addWidget(c_sub)

        header_layout.addWidget(check_icon)
        header_layout.addLayout(text_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 3 Tarjetas de métricas
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(14)
        self.card_lines = MetricCard("📄", "0", "líneas procesadas")
        self.card_deleted = MetricCard("✨", "0", "líneas eliminadas")
        self.card_time = MetricCard("⏱️", "00:00", "tiempo total")
        cards_layout.addWidget(self.card_lines)
        cards_layout.addWidget(self.card_deleted)
        cards_layout.addWidget(self.card_time)
        layout.addLayout(cards_layout)

        # Botones de Acción
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_open_file = QPushButton("📄 Abrir archivo")
        self.btn_open_file.setObjectName("PrimaryBtn")
        self.btn_open_file.clicked.connect(self._open_saved_file)

        self.btn_open_folder = QPushButton("📂 Ver en el explorador")
        self.btn_open_folder.setProperty("class", "secondary-btn")
        self.btn_open_folder.clicked.connect(self._open_output_folder)

        self.btn_to_preview = QPushButton("👁️ Ver en vista previa")
        self.btn_to_preview.setProperty("class", "secondary-btn")
        self.btn_to_preview.clicked.connect(lambda: self._switch_page(1))

        btn_row.addWidget(self.btn_open_file)
        btn_row.addWidget(self.btn_open_folder)
        btn_row.addWidget(self.btn_to_preview)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Resumen de cambios
        summary_card = QFrame()
        summary_card.setObjectName("CardContainer")
        s_layout = QVBoxLayout(summary_card)
        s_layout.setContentsMargins(20, 16, 20, 16)
        s_layout.setSpacing(8)

        s_head = QLabel("Resumen de cambios")
        s_head.setStyleSheet("font-size: 15px; font-weight: 700; color: #F8FAFC;")
        s_layout.addWidget(s_head)

        self.lbl_sum1 = QLabel("✓ Limpieza de spam, URLs e IDs aplicada")
        self.lbl_sum2 = QLabel("✓ Sincronización y estructura original conservadas")
        self.lbl_sum3 = QLabel("✓ Archivo guardado correctamente")
        for lbl in [self.lbl_sum1, self.lbl_sum2, self.lbl_sum3]:
            lbl.setStyleSheet("font-size: 13px; color: #10B981; font-weight: 500;")
            s_layout.addWidget(lbl)

        layout.addWidget(summary_card)
        layout.addStretch()
        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    # ------------------ ACCIONES Y FLUJO ------------------
    def _on_file_selected(self, subtitle_path: str, video_path: str):
        self.current_subtitle_path = subtitle_path
        self.current_video_path = video_path

        if video_path and os.path.exists(video_path):
            self.video_player.load_video(video_path)

    def _start_processing(self):
        if not self.current_subtitle_path or not os.path.exists(self.current_subtitle_path):
            QMessageBox.warning(self, "Archivo requerido", "Arrastra o selecciona un archivo de subtítulos primero.")
            return

        target_lang = self.cb_target_lang.currentData()
        source_lang = self.cb_source_lang.currentData()
        engine = self.cb_engine.currentData()
        do_translate = self.toggle_translate.isChecked()
        do_clean = self.toggle_clean.isChecked()
        parallel = self.toggle_parallel.isChecked()
        preserve_format = self.toggle_preserve.isChecked()
        target_format = None if preserve_format else "srt"

        self.modal = ProgressModal(self)
        self.modal.cancelled.connect(self._cancel_worker)
        self.modal.show()

        self.worker = ProcessWorker(
            service=self.subtitle_service,
            file_path=self.current_subtitle_path,
            do_clean=do_clean,
            do_translate=do_translate,
            target_lang=target_lang,
            source_lang=source_lang,
            engine=engine,
            target_format=target_format,
            parallel=parallel,
        )
        self.worker.step_updated.connect(self._on_worker_step)
        self.worker.completed.connect(self._on_processing_completed)
        self.worker.failed.connect(self._on_processing_failed)
        self.start_process_time = time.time()
        self.worker.start()

    def _cancel_worker(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.terminate()

    def _on_worker_step(self, step_name: str, payload: object):
        if not hasattr(self, "modal") or not self.modal.isVisible():
            return

        if step_name == "step_reading":
            self.modal.update_step(0, done=True)
            self.modal.set_progress(0.15)
        elif step_name == "step_analyzing":
            self.modal.update_step(1, done=True)
            self.modal.set_progress(0.30)
        elif step_name == "step_cleaning":
            self.modal.update_step(2, done=True)
            self.modal.set_progress(0.45)
        elif step_name == "step_translating" and isinstance(payload, tuple):
            completed, total = payload
            ratio = completed / max(1, total)
            self.modal.update_step(3, done=(completed == total), text_override=f"Traduciendo ({completed}/{total})...")
            overall = 0.45 + (ratio * 0.45)
            elapsed = time.time() - self.start_process_time
            remaining = int((elapsed / max(0.01, ratio)) - elapsed) if ratio > 0 else 0
            self.modal.set_progress(overall, remaining_seconds=max(0, remaining))
        elif step_name == "step_formatting":
            self.modal.update_step(4, done=True)
            self.modal.set_progress(0.95)
        elif step_name == "step_saving":
            self.modal.update_step(5, done=True)
            self.modal.set_progress(1.0, 0)

    def _on_processing_completed(self, result: ProcessingResult):
        if hasattr(self, "modal") and self.modal.isVisible():
            self.modal.accept()

        self.last_result = result
        base, ext = os.path.splitext(self.current_subtitle_path)
        out_path = f"{base}_processed{ext}"
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(result.output_content)
            self.saved_output_path = out_path
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar el archivo:\n{e}")
            return

        self.diff_viewer.load_subtitles(result.original_items, result.processed_items)
        self.video_player.set_subtitles(result.processed_items)

        self.card_lines.set_value(str(result.stats.total_lines))
        self.card_deleted.set_value(str(result.stats.deleted_lines))
        m = int(result.stats.elapsed_time // 60)
        s = int(result.stats.elapsed_time % 60)
        self.card_time.set_value(f"{m:02d}:{s:02d}")
        self.lbl_sum3.setText(f"✓ Guardado como: {os.path.basename(out_path)}")

        self._switch_page(6)

    def _on_processing_failed(self, error_msg: str):
        if hasattr(self, "modal") and self.modal.isVisible():
            self.modal.reject()
        QMessageBox.critical(self, "Error", f"Fallo al procesar el archivo:\n{error_msg}")

    def _start_fast_clean(self):
        if not self.current_subtitle_path:
            QMessageBox.warning(self, "Archivo requerido", "Arrastra o selecciona un archivo de subtítulos.")
            return

        self.worker = ProcessWorker(
            service=self.subtitle_service,
            file_path=self.current_subtitle_path,
            do_clean=True,
            do_translate=False,
            target_lang="es",
            source_lang="auto",
            engine="google",
        )
        self.worker.completed.connect(self._on_processing_completed)
        self.worker.failed.connect(self._on_processing_failed)
        self.worker.start()

    def _run_format_conversion(self):
        if not self.current_subtitle_path or not os.path.exists(self.current_subtitle_path):
            QMessageBox.warning(self, "Archivo requerido", "Selecciona un archivo para convertir.")
            return

        fmt_map = {"SRT (.srt)": "srt", "VTT (.vtt)": "vtt", "ASS (.ass)": "ass", "TXT (.txt)": "txt"}
        tgt_fmt = fmt_map.get(self.cb_convert_format.currentText(), "srt")

        base, _ = os.path.splitext(self.current_subtitle_path)
        out_path = f"{base}_converted.{tgt_fmt}"

        try:
            with open(self.current_subtitle_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            src_fmt = self.subtitle_service.detect_format(content, self.current_subtitle_path)
            items = self.subtitle_service.parse_subtitles(content, src_fmt)
            out_content = self.subtitle_service.format_output(items, tgt_fmt)

            with open(out_path, "w", encoding="utf-8") as out_f:
                out_f.write(out_content)

            self.saved_output_path = out_path
            QMessageBox.information(self, "Conversión completada", f"Archivo convertido y guardado en:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error en conversión", str(e))

    def _on_subtitles_edited(self, edited_items):
        if self.last_result:
            self.last_result.processed_items = edited_items
        self.video_player.set_subtitles(edited_items)

    def _on_preview_search_changed(self, text: str):
        self.diff_viewer.filter_subtitles(text)

    def _on_preview_count_changed(self, visible: int, total: int):
        if total == 0:
            self.lbl_preview_sub_counter.setText("0 subtítulos")
        elif visible == total:
            self.lbl_preview_sub_counter.setText(f"Total: {total} subtítulos")
        else:
            self.lbl_preview_sub_counter.setText(f"Mostrando {visible} de {total}")

    def _on_video_position_sync(self, pos_ms: int):
        self.diff_viewer.highlight_cue_at_ms(pos_ms, auto_scroll=self.chk_autoscroll.isChecked())

    def _export_result_file(self):
        items = self.diff_viewer.get_processed_subtitles()
        if not items and self.last_result:
            items = self.last_result.processed_items

        if not items:
            QMessageBox.information(self, "Información", "No hay subtítulo cargado para guardar.")
            return

        suggested_name = "subtitulo_editado.srt"
        if self.saved_output_path:
            suggested_name = self.saved_output_path
        elif self.current_subtitle_path:
            base, ext = os.path.splitext(self.current_subtitle_path)
            suggested_name = f"{base}_editado{ext}"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar subtítulo editado",
            suggested_name,
            "Subtítulo SRT (*.srt);;Subtítulo VTT (*.vtt);;Subtítulo ASS (*.ass);;Texto Plano (*.txt)"
        )
        if path:
            ext = os.path.splitext(path)[1].lstrip(".")
            content = self.subtitle_service.format_output(items, ext)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.saved_output_path = path
            QMessageBox.information(self, "Guardado con éxito", f"Subtítulo guardado en:\n{path}")

    def _open_burn_in_dialog(self):
        items = self.diff_viewer.get_processed_subtitles()
        if not items and self.last_result:
            items = self.last_result.processed_items

        if not items:
            QMessageBox.information(
                self,
                "Sin subtítulos",
                "No hay subtítulos disponibles para incrustar en el vídeo.\n"
                "Carga un archivo de subtítulos primero desde 'Abrir subtítulo' o procesa uno."
            )
            return

        video_path = ""
        source = self.video_player.player.source()
        if source and source.isValid() and not source.isEmpty():
            video_path = source.toLocalFile()
        elif self.current_subtitle_path:
            matching = self.drop_zone._find_matching_video(self.current_subtitle_path)
            if matching:
                video_path = matching

        if not video_path:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Seleccionar vídeo para incrustar subtítulos",
                "",
                "Archivos de vídeo (*.mp4 *.mkv *.webm *.avi *.mov *.flv *.m4v);;Todos los archivos (*.*)"
            )
            if not path:
                return
            video_path = path
            self.video_player.load_video(path)

        dialog = BurnInDialog(video_path=video_path, subtitle_items=items, parent=self)
        dialog.burn_requested.connect(self._start_burn_in_process)
        dialog.exec()

    def _start_burn_in_process(self, v_path: str, o_path: str, items: list, opts: BurnInOptions):
        modal = BurnInProgressModal(v_path, o_path, items, opts, parent=self)
        modal.exec()

    def _browse_preview_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar subtítulo para previsualizar",
            "",
            "Subtítulos (*.srt *.ass *.vtt *.txt)"
        )
        if path:
            self.current_subtitle_path = path
            fmt = self.subtitle_service.detect_format("", path)
            try:
                import copy
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                items = self.subtitle_service.parse_subtitles(content, fmt)
                edited_items = copy.deepcopy(items)
                self.diff_viewer.load_subtitles(items, edited_items)
                self.video_player.set_subtitles(edited_items)
                matching_vid = self.drop_zone._find_matching_video(path)
                if matching_vid:
                    self.video_player.load_video(matching_vid)
            except Exception as e:
                QMessageBox.critical(self, "Error al cargar subtítulo", str(e))

    def _open_saved_file(self):
        if self.saved_output_path and os.path.exists(self.saved_output_path):
            if sys.platform == "win32":
                os.startfile(self.saved_output_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.saved_output_path])
            else:
                subprocess.Popen(["xdg-open", self.saved_output_path])

    def _open_output_folder(self):
        if self.saved_output_path and os.path.exists(self.saved_output_path):
            folder = os.path.dirname(self.saved_output_path)
            if sys.platform == "win32":
                subprocess.Popen(f'explorer /select,"{os.path.normpath(self.saved_output_path)}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", self.saved_output_path])
            else:
                subprocess.Popen(["xdg-open", folder])

    # ------------------ LOTE ------------------
    def _add_batch_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar subtítulos para procesar en lote",
            "",
            "Subtítulos (*.srt *.ass *.vtt *.txt)"
        )
        for f in files:
            row = self.batch_table.rowCount()
            self.batch_table.insertRow(row)
            self.batch_table.setItem(row, 0, QTableWidgetItem(f))
            size = f"{os.path.getsize(f) / 1024:.1f} KB" if os.path.exists(f) else "0 KB"
            self.batch_table.setItem(row, 1, QTableWidgetItem(size))
            ext = os.path.splitext(f)[1].upper().lstrip(".")
            self.batch_table.setItem(row, 2, QTableWidgetItem(ext))
            self.batch_table.setItem(row, 3, QTableWidgetItem("Pendiente"))

    def _clear_batch_table(self):
        self.batch_table.setRowCount(0)

    def _run_batch_processing(self):
        rows = self.batch_table.rowCount()
        if rows == 0:
            QMessageBox.information(self, "Lote vacío", "Añade archivos a la cola primero.")
            return

        target_lang = self.cb_target_lang.currentData()
        source_lang = self.cb_source_lang.currentData()
        engine = self.cb_engine.currentData()
        do_translate = self.toggle_translate.isChecked()
        do_clean = self.toggle_clean.isChecked()
        parallel = self.toggle_parallel.isChecked()

        for row in range(rows):
            file_path = self.batch_table.item(row, 0).text()
            self.batch_table.setItem(row, 3, QTableWidgetItem("Procesando..."))
            try:
                result = self.subtitle_service.process_subtitles(
                    file_path=file_path,
                    do_clean=do_clean,
                    do_translate=do_translate,
                    target_language=target_lang,
                    source_language=source_lang,
                    engine=engine,
                    parallel=parallel,
                )
                base, ext = os.path.splitext(file_path)
                out_path = f"{base}_processed{ext}"
                with open(out_path, "w", encoding="utf-8") as out_f:
                    out_f.write(result.output_content)
                self.batch_table.setItem(row, 3, QTableWidgetItem("Completado ✓"))
            except Exception as e:
                self.batch_table.setItem(row, 3, QTableWidgetItem(f"Error: {e}"))

        QMessageBox.information(self, "Lote finalizado", "Se procesaron todos los archivos del lote.")

    # ------------------ AJUSTES ------------------
    def _load_config_values(self):
        self.txt_deepl_key.setText(self.config_service.get("deepl_api_key", ""))
        is_pro = self.config_service.get("deepl_type", "free") == "pro"
        self.rb_deepl_pro.setChecked(is_pro)
        self.rb_deepl_free.setChecked(not is_pro)

        self.txt_openai_key.setText(self.config_service.get("openai_api_key", ""))
        self.txt_openai_url.setText(self.config_service.get("openai_base_url", "https://api.openai.com/v1"))
        self.txt_openai_model.setText(self.config_service.get("openai_model", "gpt-4o-mini"))

    def _save_settings(self):
        self.config_service.set("deepl_api_key", self.txt_deepl_key.text().strip())
        self.config_service.set("deepl_type", "pro" if self.rb_deepl_pro.isChecked() else "free")
        self.config_service.set("openai_api_key", self.txt_openai_key.text().strip())
        self.config_service.set("openai_base_url", self.txt_openai_url.text().strip())
        self.config_service.set("openai_model", self.txt_openai_model.text().strip())
        QMessageBox.information(self, "Ajustes guardados", "Configuración guardada correctamente.")
