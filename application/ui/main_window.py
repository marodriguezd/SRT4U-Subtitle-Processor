# application/ui/main_window.py
import os
import subprocess
import sys
import time
from typing import Optional, List

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize
from PyQt6.QtGui import QIcon, QFont, QDesktopServices
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
from .icons import Icons
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
from ..services.i18n_service import t, get_i18n, I18nService


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
        self.i18n = get_i18n(self.config_service)
        self.translation_service = TranslationService(self.config_service)
        self.subtitle_service = SubtitleService(self.translation_service)

        self.current_subtitle_path: Optional[str] = None
        self.current_video_path: Optional[str] = None
        self.last_result: Optional[ProcessingResult] = None
        self.saved_output_path: Optional[str] = None

        self._setup_ui()
        self._load_config_values()
        self._apply_theme()
        self.i18n.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

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
        self.page_about = self._build_about_page()

        self.stack.addWidget(self.page_home)       # 0
        self.stack.addWidget(self.page_preview)    # 1
        self.stack.addWidget(self.page_clean)      # 2
        self.stack.addWidget(self.page_convert)    # 3
        self.stack.addWidget(self.page_batch)      # 4
        self.stack.addWidget(self.page_settings)   # 5
        self.stack.addWidget(self.page_completed)  # 6
        self.stack.addWidget(self.page_about)      # 7

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
            ("home", "nav.home", 0),
            ("translate", "nav.translate", 1),
            ("clean", "nav.clean", 2),
            ("convert", "nav.convert", 3),
            ("batch", "nav.batch", 4),
            ("settings", "nav.settings", 5),
            ("about", "nav.about", 7),
        ]

        for icon_name, key, page_idx in nav_items:
            btn = QPushButton(f"  {t(key)}")
            btn.setProperty("class", "nav-btn")
            btn.setProperty("page_index", page_idx)
            btn.setProperty("icon_name", icon_name)
            btn.setProperty("i18n_key", key)
            btn.setIcon(Icons.get_icon(icon_name, size=18))
            btn.setIconSize(QSize(18, 18))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=page_idx: self._switch_page(idx))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)

        layout.addStretch()
        return sidebar

    def _switch_page(self, page_index: int):
        self.stack.setCurrentIndex(page_index)
        for btn in self.nav_buttons:
            is_active = (btn.property("page_index") == page_index)
            btn.setProperty("active", "true" if is_active else "false")
            icon_name = btn.property("icon_name")
            if icon_name:
                color = Icons.DEFAULT_ACTIVE if is_active else Icons.DEFAULT_MUTED
                btn.setIcon(Icons.get_icon(icon_name, normal_color=color, active_color=Icons.DEFAULT_ACTIVE, size=18))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self._apply_theme()

    def _apply_theme(self):
        self.central_widget.setStyleSheet(Styles.get_main_style(self.dark_mode))
        if hasattr(self, "btn_theme"):
            self.btn_theme.setIcon(Icons.get_icon("sun" if self.dark_mode else "moon", normal_color="#F8FAFC", active_color="#F8FAFC", size=18))
            self.btn_theme.setIconSize(QSize(18, 18))
        self._switch_page(self.stack.currentIndex())

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

        # Header con Theme Toggle y Language Selector
        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(4)
        self.lbl_home_title = QLabel(t("home.title"))
        self.lbl_home_title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        self.lbl_home_sub = QLabel(t("home.subtitle"))
        self.lbl_home_sub.setStyleSheet("font-size: 13px; color: #94A3B8;")
        header_text.addWidget(self.lbl_home_title)
        header_text.addWidget(self.lbl_home_sub)

        # Selector de idioma global
        self.cb_top_lang = QComboBox()
        self.cb_top_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_top_lang.setToolTip(t("topbar.lang_tooltip"))
        self.cb_top_lang.setStyleSheet("""
            QComboBox {
                background: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #F8FAFC;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
                min-width: 140px;
            }
            QComboBox:hover {
                border-color: #6366F1;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #0F172A;
                color: #F8FAFC;
                selection-background-color: #6366F1;
                border: 1px solid #334155;
                padding: 4px;
            }
        """)
        self.cb_top_lang.addItem(t("topbar.lang_auto"), "auto")
        for code, meta in self.i18n.SUPPORTED_LANGUAGES.items():
            self.cb_top_lang.addItem(f"{meta['flag']} {meta['native']}", code)

        cfg_lang = self.i18n.get_configured_language()
        top_idx = self.cb_top_lang.findData(cfg_lang)
        if top_idx >= 0:
            self.cb_top_lang.setCurrentIndex(top_idx)
        self.cb_top_lang.currentIndexChanged.connect(self._on_top_lang_changed)

        self.btn_theme = QPushButton()
        self.btn_theme.setIcon(Icons.get_icon("sun" if self.dark_mode else "moon", normal_color="#F8FAFC", active_color="#F8FAFC", size=18))
        self.btn_theme.setIconSize(QSize(18, 18))
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
        header_row.addWidget(self.cb_top_lang)
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
        self.lbl_src_lang = QLabel(t("home.source_lang"))
        self.lbl_src_lang.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")
        self.cb_source_lang = QComboBox()
        self.cb_source_lang.addItem("Detectar automáticamente", "auto")
        for lang in self.translation_service.SUPPORTED_LANGUAGES:
            self.cb_source_lang.addItem(f"{lang['flag']} {lang['name']}", lang["code"])
        src_box.addWidget(self.lbl_src_lang)
        src_box.addWidget(self.cb_source_lang)

        # 2. Idioma Destino
        tgt_box = QVBoxLayout()
        tgt_box.setSpacing(6)
        self.lbl_tgt_lang = QLabel(t("home.target_lang"))
        self.lbl_tgt_lang.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")
        self.cb_target_lang = QComboBox()
        for lang in self.translation_service.SUPPORTED_LANGUAGES:
            self.cb_target_lang.addItem(f"{lang['flag']} {lang['name']}", lang["code"])
        tgt_box.addWidget(self.lbl_tgt_lang)
        tgt_box.addWidget(self.cb_target_lang)

        # 3. Modelo de Traducción
        engine_box = QVBoxLayout()
        engine_box.setSpacing(6)
        self.lbl_engine = QLabel(t("home.engine"))
        self.lbl_engine.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")
        self.cb_engine = QComboBox()
        self.cb_engine.addItem("DeepL (recomendado)", "deepl")
        self.cb_engine.addItem("Google Translate", "google")
        self.cb_engine.addItem("OpenAI / LLM", "openai")
        engine_box.addWidget(self.lbl_engine)
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

        self.card_translate = OptionCard(
            t("home.translate_title"),
            t("home.translate_desc"),
            self.toggle_translate
        )
        self.card_preserve = OptionCard(
            t("home.format_title"),
            t("home.format_desc"),
            self.toggle_preserve
        )
        self.card_clean = OptionCard(
            t("home.clean_title"),
            t("home.clean_desc"),
            self.toggle_clean
        )
        self.card_parallel = OptionCard(
            t("batch.title"),
            t("batch.subtitle"),
            self.toggle_parallel
        )

        grid_layout.addWidget(self.card_translate, 0, 0)
        grid_layout.addWidget(self.card_preserve, 0, 1)
        grid_layout.addWidget(self.card_clean, 1, 0)
        grid_layout.addWidget(self.card_parallel, 1, 1)
        layout.addLayout(grid_layout)

        # Botón de Acción Principal (🚀 Procesar archivo)
        self.btn_process = QPushButton(t("home.btn_process"))
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
        self.lbl_preview_title = QLabel(t("preview.title"))
        self.lbl_preview_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #F8FAFC;")
        self.lbl_preview_sub = QLabel(t("preview.subtitle"))
        self.lbl_preview_sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        header_text.addWidget(self.lbl_preview_title)
        header_text.addWidget(self.lbl_preview_sub)

        top_bar.addLayout(header_text)
        top_bar.addStretch()

        self.btn_open_orig = QPushButton(t("preview.btn_open"))
        self.btn_open_orig.setProperty("class", "secondary-btn")
        self.btn_open_orig.setIcon(Icons.get_icon("folder", normal_color=Icons.DEFAULT_MUTED, active_color="#FFFFFF", size=16))
        self.btn_open_orig.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_orig.clicked.connect(self._browse_preview_file)

        self.btn_export = QPushButton(t("preview.btn_save"))
        self.btn_export.setObjectName("PrimaryBtn")
        self.btn_export.setIcon(Icons.get_icon("file", normal_color="#FFFFFF", active_color="#FFFFFF", size=16))
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._export_result_file)

        self.btn_burn_in = QPushButton(t("preview.btn_burn"))
        self.btn_burn_in.setIcon(Icons.get_icon("zap", normal_color="#FFFFFF", active_color="#FFFFFF", size=16))
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
        self.preview_search_input.setPlaceholderText(t("preview.search_placeholder"))
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
        self.lbl_preview_sub_counter = QLabel(t("preview.sub_count_zero"))
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
        self.chk_autoscroll = QCheckBox(t("preview.autoscroll"))
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

        self.lbl_clean_title = QLabel(t("clean.title"))
        self.lbl_clean_title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        self.lbl_clean_sub = QLabel(t("clean.subtitle"))
        self.lbl_clean_sub.setStyleSheet("font-size: 13px; color: #94A3B8;")
        layout.addWidget(self.lbl_clean_title)
        layout.addWidget(self.lbl_clean_sub)

        self.clean_drop_zone = DropZone()
        self.clean_drop_zone.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.clean_drop_zone)

        self.btn_fast_clean = QPushButton(t("clean.btn_clean"))
        self.btn_fast_clean.setObjectName("PrimaryBtn")
        self.btn_fast_clean.setIcon(Icons.get_icon("clean", normal_color="#FFFFFF", active_color="#FFFFFF", size=16))
        self.btn_fast_clean.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fast_clean.setMinimumHeight(46)
        self.btn_fast_clean.clicked.connect(self._start_fast_clean)
        layout.addWidget(self.btn_fast_clean)

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

        self.lbl_convert_title = QLabel(t("convert.title"))
        self.lbl_convert_title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        self.lbl_convert_sub = QLabel(t("convert.subtitle"))
        self.lbl_convert_sub.setStyleSheet("font-size: 13px; color: #94A3B8;")
        layout.addWidget(self.lbl_convert_title)
        layout.addWidget(self.lbl_convert_sub)

        self.convert_drop_zone = DropZone()
        self.convert_drop_zone.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.convert_drop_zone)

        conv_card = QFrame()
        conv_card.setObjectName("CardContainer")
        c_layout = QHBoxLayout(conv_card)
        c_layout.setContentsMargins(18, 14, 18, 14)
        self.lbl_convert_target = QLabel(t("convert.target_label"))
        self.lbl_convert_target.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")
        c_layout.addWidget(self.lbl_convert_target)

        self.cb_convert_format = QComboBox()
        self.cb_convert_format.addItems(["SRT (.srt)", "VTT (.vtt)", "ASS (.ass)", "TXT (.txt)"])
        c_layout.addWidget(self.cb_convert_format)
        c_layout.addStretch()
        layout.addWidget(conv_card)

        self.btn_run_convert = QPushButton(t("convert.btn_convert"))
        self.btn_run_convert.setObjectName("PrimaryBtn")
        self.btn_run_convert.setIcon(Icons.get_icon("convert", normal_color="#FFFFFF", active_color="#FFFFFF", size=16))
        self.btn_run_convert.setMinimumHeight(46)
        self.btn_run_convert.clicked.connect(self._run_format_conversion)
        layout.addWidget(self.btn_run_convert)

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

        self.lbl_batch_title = QLabel(t("batch.title"))
        self.lbl_batch_title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        self.lbl_batch_sub = QLabel(t("batch.subtitle"))
        self.lbl_batch_sub.setStyleSheet("font-size: 13px; color: #94A3B8;")
        layout.addWidget(self.lbl_batch_title)
        layout.addWidget(self.lbl_batch_sub)

        btn_layout = QHBoxLayout()
        self.btn_add_batch = QPushButton(t("batch.btn_add"))
        self.btn_add_batch.setProperty("class", "secondary-btn")
        self.btn_add_batch.setIcon(Icons.get_icon("folder", normal_color=Icons.DEFAULT_MUTED, active_color="#FFFFFF", size=16))
        self.btn_add_batch.clicked.connect(self._add_batch_files)

        self.btn_clear_batch = QPushButton(t("batch.btn_clear"))
        self.btn_clear_batch.setProperty("class", "secondary-btn")
        self.btn_clear_batch.setIcon(Icons.get_icon("close", normal_color=Icons.DEFAULT_MUTED, active_color="#FFFFFF", size=16))
        self.btn_clear_batch.clicked.connect(self._clear_batch_table)

        btn_layout.addWidget(self.btn_add_batch)
        btn_layout.addWidget(self.btn_clear_batch)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.batch_table = QTableWidget()
        self.batch_table.setColumnCount(4)
        self.batch_table.setHorizontalHeaderLabels([
            t("batch.col_file"),
            t("batch.col_size"),
            t("batch.col_format"),
            t("batch.col_status")
        ])
        self.batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.batch_table.setMinimumHeight(240)
        layout.addWidget(self.batch_table)

        self.btn_start_batch = QPushButton(t("batch.btn_start"))
        self.btn_start_batch.setObjectName("PrimaryBtn")
        self.btn_start_batch.setIcon(Icons.get_icon("zap", normal_color="#FFFFFF", active_color="#FFFFFF", size=16))
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

        self.lbl_settings_title = QLabel(t("settings.title"))
        self.lbl_settings_title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        layout.addWidget(self.lbl_settings_title)

        # 1. Interface Language Card
        lang_card = QFrame()
        lang_card.setObjectName("CardContainer")
        l_layout = QVBoxLayout(lang_card)
        l_layout.setContentsMargins(18, 16, 18, 16)
        l_layout.setSpacing(10)

        self.lbl_lang_card_title = QLabel(t("settings.lang_card_title"))
        self.lbl_lang_card_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #F8FAFC;")
        self.lbl_lang_card_desc = QLabel(t("settings.lang_card_desc"))
        self.lbl_lang_card_desc.setStyleSheet("font-size: 12px; color: #94A3B8;")
        l_layout.addWidget(self.lbl_lang_card_title)
        l_layout.addWidget(self.lbl_lang_card_desc)

        self.cb_settings_lang = QComboBox()
        self.cb_settings_lang.addItem(t("settings.lang_auto"), "auto")
        for code, meta in self.i18n.SUPPORTED_LANGUAGES.items():
            self.cb_settings_lang.addItem(f"{meta['flag']} {meta['native']}", code)
        cfg_lang = self.i18n.get_configured_language()
        s_idx = self.cb_settings_lang.findData(cfg_lang)
        if s_idx >= 0:
            self.cb_settings_lang.setCurrentIndex(s_idx)
        self.cb_settings_lang.currentIndexChanged.connect(self._on_settings_lang_changed)
        l_layout.addWidget(self.cb_settings_lang)
        layout.addWidget(lang_card)

        # 2. DeepL Card
        deepl_card = QFrame()
        deepl_card.setObjectName("CardContainer")
        d_layout = QVBoxLayout(deepl_card)
        d_layout.setContentsMargins(18, 16, 18, 16)
        d_layout.setSpacing(10)

        self.lbl_deepl_title = QLabel(t("settings.deepl_title"))
        self.lbl_deepl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #F8FAFC;")
        self.lbl_deepl_desc = QLabel(t("settings.deepl_desc"))
        self.lbl_deepl_desc.setStyleSheet("font-size: 12px; color: #94A3B8;")
        d_layout.addWidget(self.lbl_deepl_title)
        d_layout.addWidget(self.lbl_deepl_desc)

        self.txt_deepl_key = QLineEdit()
        self.txt_deepl_key.setPlaceholderText(t("settings.deepl_placeholder"))
        d_layout.addWidget(self.txt_deepl_key)

        type_layout = QHBoxLayout()
        self.rb_deepl_free = QRadioButton(t("settings.deepl_free"))
        self.rb_deepl_pro = QRadioButton(t("settings.deepl_pro"))
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

        # 3. OpenAI / LLM Card
        openai_card = QFrame()
        openai_card.setObjectName("CardContainer")
        o_layout = QVBoxLayout(openai_card)
        o_layout.setContentsMargins(18, 16, 18, 16)
        o_layout.setSpacing(10)

        self.lbl_openai_title = QLabel(t("settings.openai_title"))
        self.lbl_openai_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #F8FAFC;")
        o_layout.addWidget(self.lbl_openai_title)

        self.txt_openai_key = QLineEdit()
        self.txt_openai_key.setPlaceholderText(t("settings.openai_key_placeholder"))
        o_layout.addWidget(self.txt_openai_key)

        self.txt_openai_url = QLineEdit()
        self.txt_openai_url.setPlaceholderText(t("settings.openai_url_placeholder"))
        o_layout.addWidget(self.txt_openai_url)

        self.txt_openai_model = QLineEdit()
        self.txt_openai_model.setPlaceholderText(t("settings.openai_model_placeholder"))
        o_layout.addWidget(self.txt_openai_model)

        layout.addWidget(openai_card)

        self.btn_save_settings = QPushButton(t("settings.btn_save"))
        self.btn_save_settings.setObjectName("PrimaryBtn")
        self.btn_save_settings.setIcon(Icons.get_icon("check", normal_color="#FFFFFF", active_color="#FFFFFF", size=16))
        self.btn_save_settings.setMinimumHeight(46)
        self.btn_save_settings.clicked.connect(self._save_settings)
        layout.addWidget(self.btn_save_settings)

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
        check_icon = QLabel()
        check_icon.setPixmap(Icons.get_pixmap("check", color=Icons.DEFAULT_SUCCESS, size=34))
        
        text_layout = QVBoxLayout()
        self.lbl_completed_title = QLabel(t("completed.title"))
        self.lbl_completed_title.setStyleSheet("font-size: 24px; font-weight: 800; color: #F8FAFC;")
        self.lbl_completed_sub = QLabel(t("completed.subtitle"))
        self.lbl_completed_sub.setStyleSheet("font-size: 13px; color: #94A3B8;")
        text_layout.addWidget(self.lbl_completed_title)
        text_layout.addWidget(self.lbl_completed_sub)

        header_layout.addWidget(check_icon)
        header_layout.addLayout(text_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 3 Tarjetas de métricas
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(14)
        self.card_lines = MetricCard("file", "0", t("completed.card_lines"))
        self.card_deleted = MetricCard("clean", "0", t("completed.card_deleted"))
        self.card_time = MetricCard("clock", "00:00", t("completed.card_time"))
        cards_layout.addWidget(self.card_lines)
        cards_layout.addWidget(self.card_deleted)
        cards_layout.addWidget(self.card_time)
        layout.addLayout(cards_layout)

        # Botones de Acción
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_open_file = QPushButton(t("completed.btn_open_file"))
        self.btn_open_file.setObjectName("PrimaryBtn")
        self.btn_open_file.setIcon(Icons.get_icon("file", normal_color="#FFFFFF", active_color="#FFFFFF", size=16))
        self.btn_open_file.clicked.connect(self._open_saved_file)

        self.btn_open_folder = QPushButton(t("completed.btn_open_folder"))
        self.btn_open_folder.setProperty("class", "secondary-btn")
        self.btn_open_folder.setIcon(Icons.get_icon("folder", normal_color=Icons.DEFAULT_MUTED, active_color="#FFFFFF", size=16))
        self.btn_open_folder.clicked.connect(self._open_output_folder)

        self.btn_to_preview = QPushButton(t("completed.btn_to_preview"))
        self.btn_to_preview.setProperty("class", "secondary-btn")
        self.btn_to_preview.setIcon(Icons.get_icon("translate", normal_color=Icons.DEFAULT_MUTED, active_color="#FFFFFF", size=16))
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

        self.lbl_summary_head = QLabel(t("completed.summary_title"))
        self.lbl_summary_head.setStyleSheet("font-size: 15px; font-weight: 700; color: #F8FAFC;")
        s_layout.addWidget(self.lbl_summary_head)

        self.lbl_sum1 = QLabel(t("completed.sum1"))
        self.lbl_sum2 = QLabel(t("completed.sum2"))
        self.lbl_sum3 = QLabel(t("completed.sum3"))
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

    # ------------------ PÁGINA: ACERCA DE ------------------
    def _btn_link_style(self) -> str:
        return """
            QPushButton {
                background: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #F8FAFC;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #334155;
                border-color: #8B5CF6;
                color: #FFFFFF;
            }
        """

    def _open_license_file(self):
        lic_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "LICENSE")
        if os.path.exists(lic_path):
            if sys.platform == "win32":
                os.startfile(lic_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", lic_path])
            else:
                subprocess.Popen(["xdg-open", lic_path])
        else:
            QDesktopServices.openUrl(QUrl("https://creativecommons.org/licenses/by-nc-sa/4.0/"))

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container.setMaximumWidth(960)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(20)

        # 1. Header con Identidad
        header_card = QFrame()
        header_card.setObjectName("CardContainer")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(24, 20, 24, 20)
        h_layout.setSpacing(20)

        logo = LogoBadge()
        logo.setFixedSize(56, 56)
        h_layout.addWidget(logo)

        h_info = QVBoxLayout()
        h_info.setSpacing(6)
        app_title = QLabel("SRT4U - Subtitle Processor")
        app_title.setStyleSheet("font-size: 22px; font-weight: 800; color: #F8FAFC;")

        tag_row = QHBoxLayout()
        tag_row.setSpacing(8)
        v_badge = QLabel("v1.0.0")
        v_badge.setStyleSheet("""
            background: #1E1B4B;
            color: #A78BFA;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 4px;
            border: 1px solid #3730A3;
        """)
        v_status = QLabel(t("about.status"))
        v_status.setStyleSheet("font-size: 12px; color: #94A3B8;")
        self.lbl_about_status = v_status
        tag_row.addWidget(v_badge)
        tag_row.addWidget(v_status)
        tag_row.addStretch()

        app_desc = QLabel(t("about.desc"))
        app_desc.setStyleSheet("font-size: 12px; color: #CBD5E1; line-height: 1.4;")
        app_desc.setWordWrap(True)
        self.lbl_about_desc = app_desc

        h_info.addWidget(app_title)
        h_info.addLayout(tag_row)
        h_info.addWidget(app_desc)
        h_layout.addLayout(h_info, stretch=1)

        layout.addWidget(header_card)

        # 2. Card: Desarrollador / About Me
        dev_card = QFrame()
        dev_card.setObjectName("CardContainer")
        d_layout = QVBoxLayout(dev_card)
        d_layout.setContentsMargins(24, 20, 24, 20)
        d_layout.setSpacing(12)

        dev_title = QLabel(t("about.author_title"))
        dev_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #F8FAFC;")
        self.lbl_dev_title = dev_title
        d_layout.addWidget(dev_title)

        dev_name = QLabel("Miguel Ángel Rodríguez Dalí")
        dev_name.setStyleSheet("font-size: 18px; font-weight: 800; color: #818CF8;")
        d_layout.addWidget(dev_name)

        dev_desc = QLabel(
            "Diseñado y desarrollado para ofrecer una experiencia rápida, privada y sin fricciones "
            "en el procesamiento y traducción de subtítulos en Fedora Linux, Windows y macOS."
        )
        dev_desc.setStyleSheet("font-size: 13px; color: #94A3B8; line-height: 1.4;")
        dev_desc.setWordWrap(True)
        d_layout.addWidget(dev_desc)

        links_row = QHBoxLayout()
        links_row.setSpacing(12)

        btn_github = QPushButton(t("about.btn_profile") + " (@marodriguezd)")
        btn_github.setStyleSheet(self._btn_link_style())
        btn_github.setIcon(Icons.get_icon("external_link", normal_color=Icons.DEFAULT_MUTED, active_color="#FFFFFF", size=14))
        btn_github.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/marodriguezd")))
        self.btn_github = btn_github
        links_row.addWidget(btn_github)

        btn_repo = QPushButton(t("about.btn_repo") + " (SRT4U)")
        btn_repo.setStyleSheet(self._btn_link_style())
        btn_repo.setIcon(Icons.get_icon("external_link", normal_color=Icons.DEFAULT_MUTED, active_color="#FFFFFF", size=14))
        btn_repo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/marodriguezd/SRT4U-Subtitle-Processor")))
        self.btn_repo = btn_repo
        links_row.addWidget(btn_repo)

        links_row.addStretch()
        d_layout.addLayout(links_row)

        layout.addWidget(dev_card)

        # 3. Card: Licencia y Términos Legales
        lic_card = QFrame()
        lic_card.setObjectName("CardContainer")
        l_layout = QVBoxLayout(lic_card)
        l_layout.setContentsMargins(24, 20, 24, 20)
        l_layout.setSpacing(12)

        lic_title = QLabel(t("about.license_title"))
        lic_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #F8FAFC;")
        self.lbl_lic_title = lic_title
        l_layout.addWidget(lic_title)

        lic_badge_row = QHBoxLayout()
        lic_badge_row.setSpacing(10)
        lic_badge = QLabel("CC BY-NC-SA 4.0")
        lic_badge.setStyleSheet("""
            background: #064E3B;
            color: #34D399;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 10px;
            border-radius: 4px;
            border: 1px solid #059669;
        """)
        lic_name = QLabel(t("about.license_name"))
        lic_name.setStyleSheet("font-size: 13px; font-weight: 600; color: #F8FAFC;")
        self.lbl_lic_name = lic_name
        lic_badge_row.addWidget(lic_badge)
        lic_badge_row.addWidget(lic_name)
        lic_badge_row.addStretch()
        l_layout.addLayout(lic_badge_row)

        lic_terms = QLabel(
            f"• <b>{t('about.perm_title')}:</b> {t('about.perm_1')}<br>"
            f"• <b>{t('about.restr_1')}</b><br>"
            f"• <b>{t('about.restr_2')}</b><br>"
            f"• <b>{t('about.restr_3')}</b>"
        )
        lic_terms.setStyleSheet("font-size: 12px; color: #CBD5E1; line-height: 1.6;")
        lic_terms.setTextFormat(Qt.TextFormat.RichText)
        lic_terms.setWordWrap(True)
        self.lbl_lic_desc = lic_terms
        l_layout.addWidget(lic_terms)

        lic_btn_row = QHBoxLayout()
        lic_btn_row.setSpacing(12)
        btn_view_lic = QPushButton(t("about.btn_open_license"))
        btn_view_lic.setStyleSheet(self._btn_link_style())
        btn_view_lic.setIcon(Icons.get_icon("file", normal_color=Icons.DEFAULT_MUTED, active_color="#FFFFFF", size=14))
        btn_view_lic.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_view_lic.clicked.connect(self._open_license_file)
        self.btn_open_license = btn_view_lic
        lic_btn_row.addWidget(btn_view_lic)

        btn_cc_web = QPushButton(t("about.btn_web_deed"))
        btn_cc_web.setStyleSheet(self._btn_link_style())
        btn_cc_web.setIcon(Icons.get_icon("globe", normal_color=Icons.DEFAULT_MUTED, active_color="#FFFFFF", size=14))
        btn_cc_web.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cc_web.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://creativecommons.org/licenses/by-nc-sa/4.0/deed.es")))
        self.btn_web_deed = btn_cc_web
        lic_btn_row.addWidget(btn_cc_web)

        lic_btn_row.addStretch()
        l_layout.addLayout(lic_btn_row)

        layout.addWidget(lic_card)
        layout.addStretch()

        scroll.setWidget(container)
        page_layout.addWidget(scroll)
        return page

    def _on_top_lang_changed(self, index: int):
        code = self.cb_top_lang.currentData()
        if code:
            self.i18n.set_language(code, save_to_config=True)
            if hasattr(self, "cb_settings_lang"):
                self.cb_settings_lang.blockSignals(True)
                s_idx = self.cb_settings_lang.findData(code)
                if s_idx >= 0:
                    self.cb_settings_lang.setCurrentIndex(s_idx)
                self.cb_settings_lang.blockSignals(False)

    def _on_settings_lang_changed(self, index: int):
        code = self.cb_settings_lang.currentData()
        if code:
            self.i18n.set_language(code, save_to_config=True)
            if hasattr(self, "cb_top_lang"):
                self.cb_top_lang.blockSignals(True)
                t_idx = self.cb_top_lang.findData(code)
                if t_idx >= 0:
                    self.cb_top_lang.setCurrentIndex(t_idx)
                self.cb_top_lang.blockSignals(False)

    def retranslate_ui(self):
        # 1. Sidebar Nav
        for btn in self.nav_buttons:
            key = btn.property("i18n_key")
            if key:
                btn.setText(f"  {t(key)}")

        # 2. Home Page
        if hasattr(self, "lbl_home_title"):
            self.lbl_home_title.setText(t("home.title"))
            self.lbl_home_sub.setText(t("home.subtitle"))
            self.lbl_src_lang.setText(t("home.source_lang"))
            self.lbl_tgt_lang.setText(t("home.target_lang"))
            self.lbl_engine.setText(t("home.engine"))
            self.card_translate.set_texts(t("home.translate_title"), t("home.translate_desc"))
            self.card_preserve.set_texts(t("home.format_title"), t("home.format_desc"))
            self.card_clean.set_texts(t("home.clean_title"), t("home.clean_desc"))
            self.card_parallel.set_texts(t("batch.title"), t("batch.subtitle"))
            self.btn_process.setText(t("home.btn_process"))
            self.drop_zone.retranslate()

        # 3. Preview / Studio Page
        if hasattr(self, "lbl_preview_title"):
            self.lbl_preview_title.setText(t("preview.title"))
            self.lbl_preview_sub.setText(t("preview.subtitle"))
            self.btn_open_orig.setText(t("preview.btn_open"))
            self.btn_export.setText(t("preview.btn_save"))
            self.btn_burn_in.setText(t("preview.btn_burn"))
            self.preview_search_input.setPlaceholderText(t("preview.search_placeholder"))
            self.chk_autoscroll.setText(t("preview.autoscroll"))
            self.diff_viewer.retranslate()
            self.video_player.retranslate()

        # 4. Clean Page
        if hasattr(self, "lbl_clean_title"):
            self.lbl_clean_title.setText(t("clean.title"))
            self.lbl_clean_sub.setText(t("clean.subtitle"))
            self.btn_fast_clean.setText(t("clean.btn_clean"))
            self.clean_drop_zone.retranslate()

        # 5. Convert Page
        if hasattr(self, "lbl_convert_title"):
            self.lbl_convert_title.setText(t("convert.title"))
            self.lbl_convert_sub.setText(t("convert.subtitle"))
            self.lbl_convert_target.setText(t("convert.target_label"))
            self.btn_run_convert.setText(t("convert.btn_convert"))
            self.convert_drop_zone.retranslate()

        # 6. Batch Page
        if hasattr(self, "lbl_batch_title"):
            self.lbl_batch_title.setText(t("batch.title"))
            self.lbl_batch_sub.setText(t("batch.subtitle"))
            self.btn_add_batch.setText(t("batch.btn_add"))
            self.btn_clear_batch.setText(t("batch.btn_clear"))
            self.batch_table.setHorizontalHeaderLabels([
                t("batch.col_file"),
                t("batch.col_size"),
                t("batch.col_format"),
                t("batch.col_status")
            ])
            self.btn_start_batch.setText(t("batch.btn_start"))

        # 7. Settings Page
        if hasattr(self, "lbl_settings_title"):
            self.lbl_settings_title.setText(t("settings.title"))
            self.lbl_lang_card_title.setText(t("settings.lang_card_title"))
            self.lbl_lang_card_desc.setText(t("settings.lang_card_desc"))
            self.lbl_deepl_title.setText(t("settings.deepl_title"))
            self.lbl_deepl_desc.setText(t("settings.deepl_desc"))
            self.txt_deepl_key.setPlaceholderText(t("settings.deepl_placeholder"))
            self.rb_deepl_free.setText(t("settings.deepl_free"))
            self.rb_deepl_pro.setText(t("settings.deepl_pro"))
            self.lbl_openai_title.setText(t("settings.openai_title"))
            self.txt_openai_key.setPlaceholderText(t("settings.openai_key_placeholder"))
            self.txt_openai_url.setPlaceholderText(t("settings.openai_url_placeholder"))
            self.txt_openai_model.setPlaceholderText(t("settings.openai_model_placeholder"))
            self.btn_save_settings.setText(t("settings.btn_save"))

        # 8. Completed Page
        if hasattr(self, "lbl_completed_title"):
            self.lbl_completed_title.setText(t("completed.title"))
            self.lbl_completed_sub.setText(t("completed.subtitle"))
            self.card_lines.set_label(t("completed.card_lines"))
            self.card_deleted.set_label(t("completed.card_deleted"))
            self.card_time.set_label(t("completed.card_time"))
            self.btn_open_file.setText(t("completed.btn_open_file"))
            self.btn_open_folder.setText(t("completed.btn_open_folder"))
            self.btn_to_preview.setText(t("completed.btn_to_preview"))
            self.lbl_summary_head.setText(t("completed.summary_title"))
            self.lbl_sum1.setText(t("completed.sum1"))
            self.lbl_sum2.setText(t("completed.sum2"))
            self.lbl_sum3.setText(t("completed.sum3"))

        # 9. About Page
        if hasattr(self, "lbl_about_status"):
            self.lbl_about_status.setText(t("about.status"))
            self.lbl_about_desc.setText(t("about.desc"))
            self.lbl_dev_title.setText(t("about.author_title"))
            self.btn_github.setText(t("about.btn_profile") + " (@marodriguezd)")
            self.btn_repo.setText(t("about.btn_repo") + " (SRT4U)")
            self.lbl_lic_title.setText(t("about.license_title"))
            self.lbl_lic_name.setText(t("about.license_name"))
            self.lbl_lic_desc.setText(
                f"• <b>{t('about.perm_title')}:</b> {t('about.perm_1')}<br>"
                f"• <b>{t('about.restr_1')}</b><br>"
                f"• <b>{t('about.restr_2')}</b><br>"
                f"• <b>{t('about.restr_3')}</b>"
            )
            self.btn_open_license.setText(t("about.btn_open_license"))
            self.btn_web_deed.setText(t("about.btn_web_deed"))
