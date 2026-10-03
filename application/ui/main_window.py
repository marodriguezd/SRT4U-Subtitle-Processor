import copy
import os
import sys
import threading
import time
from typing import Optional, List

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QStackedWidget,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
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
from ..platform_utils import open_path, reveal_path
from .file_dialogs import ask_open_file, ask_open_files, ask_save_file
from .message_boxes import ThemedMessageBox
from ..services.config_service import ConfigService
from ..services.subtitle_service import (
    SubtitleCancelledError,
    SubtitleService,
    ProcessingResult,
)
from ..services.translation_service import TranslationService
from ..services.transcription_providers import (
    TranscriptionCancelledError,
    TranscriptionError,
)
from ..services.media_pipeline import (
    MediaPipeline,
    PipelineConfig,
    PipelineConfigError,
    record_pipeline_result,
)
from ..services.transcription_service import MEDIA_EXTENSIONS, TranscriptionService
from ..services.i18n_service import t, get_i18n
from ..version import (
    APP_AUTHOR_NAME,
    APP_GITHUB_OWNER,
    APP_GITHUB_PROFILE_URL,
    APP_GITHUB_REPO_URL,
)
from ..logging_setup import get_logger

logger = get_logger("ui")

#: How long ``closeEvent`` waits for a cooperative cancellation to land before
#: it defers the window close. Long enough for an in-flight provider call to
#: return, short enough that the user does not think the app has hung.
CLOSE_GRACE_SECONDS = 5.0


def _is_running_thread(candidate) -> bool:
    """True when ``candidate`` is a background thread that is still running.

    Duck-typed on ``isRunning`` so the close policy can be exercised with a
    stand-in worker in tests, without ever requiring a live ``QThread``.
    """
    return (
        candidate is not None
        and callable(getattr(candidate, "isRunning", None))
        and bool(candidate.isRunning())
    )


def _nav_label(key: str) -> str:
    """Sidebar label text.

    The icon/text gap is owned by the ``nav-btn`` QSS padding and the style,
    never by literal leading spaces in the label (layout hack removed).
    """
    return t(key)


class ProcessWorker(QThread):
    """Subtitle processing off the UI thread with cooperative cancellation.

    Deep-audit H3: this used to be cancelled with ``QThread.terminate()``,
    which killed the thread while it was inside a ``ThreadPoolExecutor``. The
    pool's ``__exit__`` never ran, its non-daemon worker threads survived the
    kill and kept calling the provider and writing to the *shared*
    ``SubtitleService``. It now uses the same ``cancel_event`` model as
    ``TranscribeWorker`` and ``PipelineWorker``, so the pool always shuts down
    cleanly and no zombie thread can write into the next job.
    """

    step_updated = pyqtSignal(str, object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

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
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

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
                cancel_event=self.cancel_event,
            )
            if self.cancel_event.is_set():
                self.cancelled.emit()
                return
            self.completed.emit(result)
        except SubtitleCancelledError:
            self.cancelled.emit()
        except Exception:
            logger.exception("Fallo al procesar el subtítulo")
            self.failed.emit(t("worker.error_processing"))


class TranscribeWorker(QThread):
    """Whisper transcription off the UI thread with graceful cancellation."""

    step_updated = pyqtSignal(str, object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        service: TranscriptionService,
        media_path: str,
        model: str,
        language: str,
        device: str,
    ):
        super().__init__()
        self.service = service
        self.media_path = media_path
        self.model = model
        self.language = language
        self.device = device
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        def callback(event_name: str, payload: object):
            self.step_updated.emit(event_name, payload)

        try:
            result = self.service.transcribe_file(
                self.media_path,
                provider_name="whisper",
                model=self.model,
                language=self.language,
                device=self.device,
                progress_callback=callback,
                cancel_event=self.cancel_event,
            )
            if self.cancel_event.is_set():
                self.failed.emit(t("transcribe.cancelled"))
                return
            self.completed.emit(result)
        except TranscriptionCancelledError:
            self.failed.emit(t("transcribe.cancelled"))
        except TranscriptionError as e:
            logger.warning("Fallo de transcripción (%s)", e.error_type)
            self.failed.emit(e.error_type)
        except Exception:
            logger.exception("Fallo inesperado al transcribir el medio")
            self.failed.emit(t("worker.error_transcribe"))


class PipelineWorker(QThread):
    """Full media pipeline off the UI thread; cooperative cancellation."""

    step_updated = pyqtSignal(str, object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, config: PipelineConfig):
        super().__init__()
        self.config = config
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        def callback(event_name: str, payload: object):
            self.step_updated.emit(event_name, payload)

        try:
            result = MediaPipeline().run(
                self.config,
                progress_callback=callback,
                cancel_event=self.cancel_event,
            )
            if self.cancel_event.is_set() or result.cancelled:
                self.failed.emit(t("pipeline.cancelled"))
                return
            self.completed.emit(result)
        except PipelineConfigError as e:
            logger.warning("Configuración de pipeline no válida (%s)", type(e).__name__)
            self.failed.emit(t("worker.error_pipeline_config"))
        except Exception:
            logger.exception("Fallo inesperado en la pipeline")
            self.failed.emit(t("worker.error_pipeline_internal"))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # El título de ventana lo fija `retranslate_ui()` según el idioma activo
        self.setMinimumSize(980, 640)
        self._apply_initial_geometry()

        self.dark_mode = True
        self.config_service = ConfigService()
        self.i18n = get_i18n(self.config_service)
        self.translation_service = TranslationService(self.config_service)
        self.subtitle_service = SubtitleService(self.translation_service)
        self.transcription_service = TranscriptionService(
            self.config_service, self.subtitle_service
        )

        self.current_subtitle_path: Optional[str] = None
        self.current_media_path: Optional[str] = None
        self.transcribe_cancelled = False
        self.pipeline_input_path: Optional[str] = None
        self.pipeline_video_output: Optional[str] = None
        self.pipeline_cancelled = False
        self.last_result: Optional[ProcessingResult] = None
        self.saved_output_path: Optional[str] = None

        self._setup_ui()
        self._load_config_values()
        self._apply_theme()
        self.i18n.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

        logger.info(
            "Interfaz inicializada (tema=%s, idioma=%s)",
            "oscuro" if self.dark_mode else "claro",
            self.i18n.current_language,
        )
        if self.config_service.load_error:
            # La configuración no se pudo leer y se han restaurado los valores por defecto
            ThemedMessageBox.warning(
                self,
                t("alert.settings_load_error_title"),
                t(
                    "alert.settings_load_error_desc",
                    path=self.config_service.config_file,
                ),
            )

    def _apply_initial_geometry(self):
        """Ajusta el tamaño inicial al espacio disponible de la pantalla."""
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = max(980, min(1280, int(available.width() * 0.85)))
            height = max(640, min(860, int(available.height() * 0.85)))
        else:
            width, height = 1200, 780
        self.resize(width, height)

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
        self.page_history = self._build_history_page()
        self.page_transcribe = self._build_transcribe_page()
        self.page_pipeline = self._build_pipeline_page()

        self.stack.addWidget(self.page_home)  # 0
        self.stack.addWidget(self.page_preview)  # 1
        self.stack.addWidget(self.page_clean)  # 2
        self.stack.addWidget(self.page_convert)  # 3
        self.stack.addWidget(self.page_batch)  # 4
        self.stack.addWidget(self.page_settings)  # 5
        self.stack.addWidget(self.page_completed)  # 6
        self.stack.addWidget(self.page_about)  # 7
        self.stack.addWidget(self.page_history)  # 8
        self.stack.addWidget(self.page_transcribe)  # 9
        self.stack.addWidget(self.page_pipeline)  # 10

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
        app_title.setStyleSheet(
            f"font-size: 18px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_app_sub = QLabel(t("app.subtitle"))
        self.lbl_app_sub.setStyleSheet(
            f"font-size: 11px; color: {Styles.ACCENT_LIGHT}; font-weight: 500;"
        )
        app_sub = self.lbl_app_sub
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
            ("play", "nav.transcribe", 9),
            ("zap", "nav.pipeline", 10),
            ("clock", "nav.history", 8),
            ("settings", "nav.settings", 5),
            ("about", "nav.about", 7),
        ]

        for icon_name, key, page_idx in nav_items:
            btn = QPushButton(_nav_label(key))
            btn.setProperty("class", "nav-btn")
            btn.setProperty("page_index", page_idx)
            btn.setProperty("icon_name", icon_name)
            btn.setProperty("i18n_key", key)
            btn.setIcon(
                Icons.get_icon(
                    icon_name,
                    normal_color=(
                        Styles.NAV_IDLE_ICON_DARK
                        if self.dark_mode
                        else Styles.NAV_IDLE_ICON_LIGHT
                    ),
                    active_color=(
                        Styles.NAV_ACTIVE_ICON_DARK
                        if self.dark_mode
                        else Styles.NAV_ACTIVE_ICON_LIGHT
                    ),
                    size=18,
                )
            )
            btn.setIconSize(QSize(18, 18))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=page_idx: self._switch_page(idx))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)

        layout.addStretch()
        return sidebar

    def _active_workers(self) -> List[QThread]:
        """Every background thread this window currently owns."""
        found: List[QThread] = []
        for name in ("worker", "transcribe_worker", "pipeline_worker"):
            candidate = getattr(self, name, None)
            if _is_running_thread(candidate):
                found.append(candidate)
        dialog = getattr(self, "burn_dialog", None)
        if dialog is not None:
            candidate = getattr(dialog, "worker", None)
            if _is_running_thread(candidate):
                found.append(candidate)
        return found

    def closeEvent(self, event):  # noqa: N802 - Qt naming
        """Never let Qt destroy a QThread that is still running.

        Deep-audit M11: there was no ``closeEvent`` at all, so closing the
        window during a transcription, a pipeline or a burn-in destroyed a
        running ``QThread``. That aborts with "QThread: Destroyed while thread
        is still running" and orphans the FFmpeg child plus its ``srt4u_burn_*``
        temp directory, because the worker's ``finally`` never runs.

        Policy: ask every worker to cancel cooperatively, pump the event loop
        until they stop, and if any refuses, *refuse the close* rather than
        terminate it. Losing a queued window close is much cheaper than
        destroying a live thread.
        """
        workers = self._active_workers()
        if not workers:
            event.accept()
            return

        logger.warning(
            "Cierre solicitado con %s worker(s) activo(s): cancelando",
            len(workers),
        )
        for worker in workers:
            cancel = getattr(worker, "cancel", None)
            if callable(cancel):
                try:
                    cancel()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "No se pudo cancelar un worker (%s)", type(exc).__name__
                    )

        deadline = time.monotonic() + CLOSE_GRACE_SECONDS
        while time.monotonic() < deadline:
            if not any(worker.isRunning() for worker in workers):
                break
            QApplication.processEvents()
            time.sleep(0.02)

        still_running = [worker for worker in workers if worker.isRunning()]
        if still_running:
            logger.error(
                "Cierre pospuesto: %s worker(s) no terminaron a tiempo",
                len(still_running),
            )
            event.ignore()
            return
        event.accept()

    def _switch_page(self, page_index: int):
        self.stack.setCurrentIndex(page_index)
        # Los iconos de la barra lateral también cambian con el tema: los colores
        # por defecto de `Icons` están calibrados para el fondo oscuro.
        active_color = (
            Styles.NAV_ACTIVE_ICON_DARK
            if self.dark_mode
            else Styles.NAV_ACTIVE_ICON_LIGHT
        )
        idle_color = (
            Styles.NAV_IDLE_ICON_DARK if self.dark_mode else Styles.NAV_IDLE_ICON_LIGHT
        )
        for btn in self.nav_buttons:
            is_active = btn.property("page_index") == page_index
            btn.setProperty("active", "true" if is_active else "false")
            icon_name = btn.property("icon_name")
            if icon_name:
                color = active_color if is_active else idle_color
                btn.setIcon(
                    Icons.get_icon(
                        icon_name,
                        normal_color=color,
                        active_color=active_color,
                        size=18,
                    )
                )
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self._apply_theme()

    def _apply_theme(self):
        # El tema activo se registra en Styles para que los diálogos del sistema
        # (archivos, mensajes, tooltips) se pinten con los mismos colores.
        Styles.set_dark(self.dark_mode)
        self.central_widget.setStyleSheet(Styles.get_main_style(self.dark_mode))
        Styles.retint_inline_text(self.central_widget, self.dark_mode)
        if hasattr(self, "btn_theme"):
            self.btn_theme.setIcon(
                Icons.get_icon(
                    "sun" if self.dark_mode else "moon",
                    normal_color="#F8FAFC",
                    active_color="#F8FAFC",
                    size=18,
                )
            )
            self.btn_theme.setIconSize(QSize(18, 18))
        # Los tooltips se estilizan a nivel de aplicación: se reapuntan al tema activo
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(Styles.tooltip_qss(self.dark_mode))
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
        self.lbl_home_title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_home_sub = QLabel(t("home.subtitle"))
        self.lbl_home_sub.setStyleSheet(f"font-size: 13px; color: {Styles.TEXT_MUTED};")
        self.lbl_home_sub.setWordWrap(True)
        header_text.addWidget(self.lbl_home_title)
        header_text.addWidget(self.lbl_home_sub)

        # Selector de idioma global
        self.cb_top_lang = QComboBox()
        self.cb_top_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_top_lang.setToolTip(t("topbar.lang_tooltip"))
        self.cb_top_lang.setStyleSheet(f"""
            QComboBox {{
                background: {Styles.SURFACE_RAISED};
                border: 1px solid {Styles.BORDER};
                border-radius: 8px;
                color: {Styles.TEXT};
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
                min-width: 140px;
            }}
            QComboBox:hover {{
                border-color: {Styles.PRIMARY};
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {Styles.SURFACE};
                color: {Styles.TEXT};
                selection-background-color: {Styles.PRIMARY};
                border: 1px solid {Styles.BORDER};
                padding: 4px;
            }}
        """)
        self.cb_top_lang.addItem(t("topbar.lang_auto"), "auto")
        for code, meta in self.i18n.SUPPORTED_LANGUAGES.items():
            self.cb_top_lang.addItem(meta["native"], code)

        cfg_lang = self.i18n.get_configured_language()
        top_idx = self.cb_top_lang.findData(cfg_lang)
        if top_idx >= 0:
            self.cb_top_lang.setCurrentIndex(top_idx)
        self.cb_top_lang.currentIndexChanged.connect(self._on_top_lang_changed)

        self.btn_theme = QPushButton()
        self.btn_theme.setToolTip(t("topbar.theme_tooltip"))
        self.btn_theme.setAccessibleName(t("topbar.theme_tooltip"))
        self.btn_theme.setIcon(
            Icons.get_icon(
                "sun" if self.dark_mode else "moon",
                normal_color="#F8FAFC",
                active_color="#F8FAFC",
                size=18,
            )
        )
        self.btn_theme.setIconSize(QSize(18, 18))
        self.btn_theme.setFixedSize(38, 38)
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.setStyleSheet(f"""
            QPushButton {{
                background: {Styles.SURFACE_RAISED};
                border: 1px solid {Styles.BORDER};
                border-radius: 19px;
                font-size: 16px;
                color: {Styles.TEXT};
            }}
            QPushButton:hover {{
                background: {Styles.BORDER};
                border-color: {Styles.PRIMARY};
            }}
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
        self.lbl_src_lang.setStyleSheet(
            f"font-weight: 700; font-size: 13px; color: {Styles.TEXT};"
        )
        self.cb_source_lang = QComboBox()
        self.cb_source_lang.addItem(t("home.lang_auto"), "auto")
        for lang in self.translation_service.SUPPORTED_LANGUAGES:
            self.cb_source_lang.addItem(lang["name"], lang["code"])
        src_box.addWidget(self.lbl_src_lang)
        src_box.addWidget(self.cb_source_lang)

        # 2. Idioma Destino
        tgt_box = QVBoxLayout()
        tgt_box.setSpacing(6)
        self.lbl_tgt_lang = QLabel(t("home.target_lang"))
        self.lbl_tgt_lang.setStyleSheet(
            f"font-weight: 700; font-size: 13px; color: {Styles.TEXT};"
        )
        self.cb_target_lang = QComboBox()
        for lang in self.translation_service.SUPPORTED_LANGUAGES:
            self.cb_target_lang.addItem(lang["name"], lang["code"])
        tgt_box.addWidget(self.lbl_tgt_lang)
        tgt_box.addWidget(self.cb_target_lang)

        # 3. Modelo de Traducción
        engine_box = QVBoxLayout()
        engine_box.setSpacing(6)
        self.lbl_engine = QLabel(t("home.engine"))
        self.lbl_engine.setStyleSheet(
            f"font-weight: 700; font-size: 13px; color: {Styles.TEXT};"
        )
        self.cb_engine = QComboBox()
        self.cb_engine.addItem(t("home.engine_deepl"), "deepl")
        self.cb_engine.addItem(t("home.engine_google"), "google")
        self.cb_engine.addItem(t("home.engine_openai"), "openai")
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
            t("home.translate_title"), t("home.translate_desc"), self.toggle_translate
        )
        self.card_preserve = OptionCard(
            t("home.format_title"), t("home.format_desc"), self.toggle_preserve
        )
        self.card_clean = OptionCard(
            t("home.clean_title"), t("home.clean_desc"), self.toggle_clean
        )
        self.card_parallel = OptionCard(
            t("batch.title"), t("batch.subtitle"), self.toggle_parallel
        )

        grid_layout.addWidget(self.card_translate, 0, 0)
        grid_layout.addWidget(self.card_preserve, 0, 1)
        grid_layout.addWidget(self.card_clean, 1, 0)
        grid_layout.addWidget(self.card_parallel, 1, 1)
        layout.addLayout(grid_layout)

        # Botón de Acción Principal
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
        self.lbl_preview_title.setStyleSheet(
            f"font-size: 18px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_preview_sub = QLabel(t("preview.subtitle"))
        self.lbl_preview_sub.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_preview_sub.setWordWrap(True)
        header_text.addWidget(self.lbl_preview_title)
        header_text.addWidget(self.lbl_preview_sub)

        top_bar.addLayout(header_text)
        top_bar.addStretch()

        self.btn_open_orig = QPushButton(t("preview.btn_open"))
        self.btn_open_orig.setProperty("class", "secondary-btn")
        self.btn_open_orig.setIcon(
            Icons.get_icon(
                "folder",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=16,
            )
        )
        self.btn_open_orig.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_orig.clicked.connect(self._browse_preview_file)

        self.btn_export = QPushButton(t("preview.btn_save"))
        self.btn_export.setObjectName("PrimaryBtn")
        self.btn_export.setIcon(
            Icons.get_icon(
                "file", normal_color="#FFFFFF", active_color="#FFFFFF", size=16
            )
        )
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._export_result_file)

        self.btn_burn_in = QPushButton(t("preview.btn_burn"))
        self.btn_burn_in.setIcon(
            Icons.get_icon(
                "zap", normal_color="#FFFFFF", active_color="#FFFFFF", size=16
            )
        )
        self.btn_burn_in.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_burn_in.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Styles.ACCENT}, stop:1 #EC4899);
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 700;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Styles.ACCENT_HOVER}, stop:1 #DB2777);
            }}
        """)
        self.btn_burn_in.clicked.connect(self._open_burn_in_dialog)

        top_bar.addWidget(self.btn_open_orig)
        top_bar.addWidget(self.btn_export)
        top_bar.addWidget(self.btn_burn_in)
        page_layout.addLayout(top_bar)

        # 2. Control & Search Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet(f"""
            QFrame {{
                background: {Styles.SURFACE};
                border: 1px solid {Styles.SURFACE_RAISED};
                border-radius: 8px;
            }}
        """)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(14)

        # Search bar
        self.preview_search_input = QLineEdit()
        self.preview_search_input.setPlaceholderText(t("preview.search_placeholder"))
        self.preview_search_input.setClearButtonEnabled(True)
        self.preview_search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {Styles.SURFACE_RAISED};
                border: 1px solid {Styles.BORDER};
                border-radius: 6px;
                color: {Styles.TEXT};
                padding: 6px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {Styles.ACCENT};
                background: #1A2234;
            }}
        """)
        self.preview_search_input.textChanged.connect(self._on_preview_search_changed)
        tb_layout.addWidget(self.preview_search_input, stretch=2)

        # Counter badge
        self.lbl_preview_sub_counter = QLabel(t("preview.sub_count_zero"))
        self.lbl_preview_sub_counter.setStyleSheet(f"""
            QLabel {{
                background: {Styles.SURFACE_RAISED};
                color: {Styles.TEXT_MUTED};
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid {Styles.BORDER};
            }}
        """)
        tb_layout.addWidget(self.lbl_preview_sub_counter)

        # Auto-scroll toggle
        self.chk_autoscroll = QCheckBox(t("preview.autoscroll"))
        self.chk_autoscroll.setChecked(True)
        self.chk_autoscroll.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_autoscroll.setStyleSheet(f"""
            QCheckBox {{
                color: {Styles.TEXT_SUBTLE};
                font-size: 12px;
                font-weight: 600;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #475569;
                background: {Styles.SURFACE_RAISED};
            }}
            QCheckBox::indicator:checked {{
                background: {Styles.ACCENT};
                border-color: {Styles.ACCENT};
            }}
        """)
        tb_layout.addWidget(self.chk_autoscroll)

        page_layout.addWidget(toolbar)

        # 3. Cinema Splitter (Video Player on TOP, Subtitle Diff Viewer on BOTTOM)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet(f"""
            QSplitter::handle:vertical {{
                background-color: {Styles.SURFACE_RAISED};
                height: 6px;
                margin: 2px 20px;
                border-radius: 3px;
            }}
            QSplitter::handle:vertical:hover {{
                background-color: {Styles.ACCENT};
            }}
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
        self.lbl_clean_title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_clean_sub = QLabel(t("clean.subtitle"))
        self.lbl_clean_sub.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_clean_sub.setWordWrap(True)
        layout.addWidget(self.lbl_clean_title)
        layout.addWidget(self.lbl_clean_sub)

        self.clean_drop_zone = DropZone()
        self.clean_drop_zone.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.clean_drop_zone)

        self.btn_fast_clean = QPushButton(t("clean.btn_clean"))
        self.btn_fast_clean.setObjectName("PrimaryBtn")
        self.btn_fast_clean.setIcon(
            Icons.get_icon(
                "clean", normal_color="#FFFFFF", active_color="#FFFFFF", size=16
            )
        )
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
        self.lbl_convert_title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_convert_sub = QLabel(t("convert.subtitle"))
        self.lbl_convert_sub.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_convert_sub.setWordWrap(True)
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
        self.lbl_convert_target.setStyleSheet(
            f"font-weight: 700; font-size: 13px; color: {Styles.TEXT};"
        )
        c_layout.addWidget(self.lbl_convert_target)

        self.cb_convert_format = QComboBox()
        self.cb_convert_format.addItems(
            ["SRT (.srt)", "VTT (.vtt)", "ASS (.ass)", "TXT (.txt)"]
        )
        c_layout.addWidget(self.cb_convert_format)
        c_layout.addStretch()
        layout.addWidget(conv_card)

        self.btn_run_convert = QPushButton(t("convert.btn_convert"))
        self.btn_run_convert.setObjectName("PrimaryBtn")
        self.btn_run_convert.setIcon(
            Icons.get_icon(
                "convert", normal_color="#FFFFFF", active_color="#FFFFFF", size=16
            )
        )
        self.btn_run_convert.setMinimumHeight(46)
        self.btn_run_convert.clicked.connect(self._run_format_conversion)
        layout.addWidget(self.btn_run_convert)

        layout.addStretch()
        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    # ------------------ PÁGINA: TRANSCRIPCIÓN ------------------
    def _build_transcribe_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        container = QWidget()
        container.setMaximumWidth(1020)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        self.lbl_transcribe_title = QLabel(
            t("transcribe.title", "Transcribir multimedia")
        )
        self.lbl_transcribe_title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_transcribe_sub = QLabel(
            t(
                "transcribe.subtitle",
                "Convierte audio o vídeo en subtítulos con Whisper local. "
                "El resultado alimenta Analytics, QA, limpieza y traducción.",
            )
        )
        self.lbl_transcribe_sub.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_transcribe_sub.setWordWrap(True)
        layout.addWidget(self.lbl_transcribe_title)
        layout.addWidget(self.lbl_transcribe_sub)

        self.lbl_transcribe_avail = QLabel()
        self.lbl_transcribe_avail.setWordWrap(True)
        layout.addWidget(self.lbl_transcribe_avail)

        file_card = QFrame()
        file_card.setObjectName("CardContainer")
        f_layout = QHBoxLayout(file_card)
        f_layout.setContentsMargins(18, 14, 18, 14)
        self.lbl_transcribe_file = QLabel(
            t("transcribe.no_file", "Ningún archivo seleccionado")
        )
        self.lbl_transcribe_file.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED};"
        )
        f_layout.addWidget(self.lbl_transcribe_file, stretch=1)
        self.btn_choose_media = QPushButton(
            t("transcribe.btn_choose", "Elegir archivo")
        )
        self.btn_choose_media.setProperty("class", "secondary-btn")
        self.btn_choose_media.setIcon(
            Icons.get_icon(
                "folder",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=16,
            )
        )
        self.btn_choose_media.clicked.connect(self._choose_transcribe_file)
        f_layout.addWidget(self.btn_choose_media)
        layout.addWidget(file_card)

        opts_card = QFrame()
        opts_card.setObjectName("CardContainer")
        o_layout = QGridLayout(opts_card)
        o_layout.setContentsMargins(18, 14, 18, 14)
        o_layout.setHorizontalSpacing(12)
        o_layout.setVerticalSpacing(10)
        self.lbl_transcribe_model = QLabel(t("transcribe.model", "Modelo Whisper"))
        self.cb_transcribe_model = QComboBox()
        self.cb_transcribe_model.addItems(
            ["tiny", "base", "small", "medium", "large-v3", "turbo"]
        )
        self.cb_transcribe_model.setCurrentText("small")
        self.lbl_transcribe_lang = QLabel(
            t("transcribe.language", "Idioma de origen (auto)")
        )
        self.le_transcribe_lang = QLineEdit("auto")
        self.le_transcribe_lang.setMaximumWidth(140)
        self.lbl_transcribe_format = QLabel(t("transcribe.format", "Formato"))
        self.cb_transcribe_format = QComboBox()
        self.cb_transcribe_format.addItems(["SRT (.srt)", "VTT (.vtt)"])
        self.lbl_transcribe_device = QLabel(t("transcribe.device", "Dispositivo"))
        self.cb_transcribe_device = QComboBox()
        self.cb_transcribe_device.addItems(["auto", "cpu", "cuda"])
        o_layout.addWidget(self.lbl_transcribe_model, 0, 0)
        o_layout.addWidget(self.cb_transcribe_model, 0, 1)
        o_layout.addWidget(self.lbl_transcribe_lang, 0, 2)
        o_layout.addWidget(self.le_transcribe_lang, 0, 3)
        o_layout.addWidget(self.lbl_transcribe_format, 1, 0)
        o_layout.addWidget(self.cb_transcribe_format, 1, 1)
        o_layout.addWidget(self.lbl_transcribe_device, 1, 2)
        o_layout.addWidget(self.cb_transcribe_device, 1, 3)
        layout.addWidget(opts_card)

        self.btn_start_transcribe = QPushButton(
            t("transcribe.btn_start", "Transcribir")
        )
        self.btn_start_transcribe.setObjectName("PrimaryBtn")
        self.btn_start_transcribe.setIcon(
            Icons.get_icon(
                "play", normal_color="#FFFFFF", active_color="#FFFFFF", size=16
            )
        )
        self.btn_start_transcribe.setMinimumHeight(46)
        self.btn_start_transcribe.clicked.connect(self._start_transcription)
        layout.addWidget(self.btn_start_transcribe)

        layout.addStretch()
        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._refresh_transcribe_availability()
        return page

    def _refresh_transcribe_availability(self):
        try:
            from ..services.transcription_whisper import WHISPER_MODELS

            models = ", ".join(WHISPER_MODELS)
        except Exception:
            models = "tiny, base, small, medium, large-v3, turbo"
        try:
            self.transcription_service.check_available("whisper")
            available = True
        except Exception:
            available = False
        if available:
            self.lbl_transcribe_avail.setText(
                t(
                    "transcribe.avail_ok",
                    "Whisper disponible localmente. Modelos: {models}. "
                    "El modelo se descarga una vez si no está en caché.",
                    models=models,
                )
            )
            self.btn_start_transcribe.setEnabled(True)
        else:
            self.lbl_transcribe_avail.setText(
                t(
                    "transcribe.avail_missing",
                    "Whisper no instalado: python -m pip install '.[transcription]'. "
                    "La transcripción es 100% local.",
                )
            )
            self.btn_start_transcribe.setEnabled(False)

    def _transcribe_media_filter(self) -> str:
        patterns = " ".join(f"*{ext}" for ext in sorted(MEDIA_EXTENSIONS))
        return f"{t('transcribe.media_filter', patterns=patterns)};;{t('dialog.all_files')}"

    def _choose_transcribe_file(self):
        chosen = ask_open_file(
            self,
            t("transcribe.choose_title", "Elegir audio o vídeo"),
            self._transcribe_media_filter(),
        )
        if chosen:
            self.current_media_path = chosen
            self.lbl_transcribe_file.setText(os.path.basename(chosen))

    def _start_transcription(self):
        # D6: one transcription at a time; a second start must not replace the
        # running worker (they would share the stateful TranscriptionService).
        worker = getattr(self, "transcribe_worker", None)
        if worker is not None and worker.isRunning():
            return
        if not self.current_media_path or not os.path.exists(self.current_media_path):
            ThemedMessageBox.warning(
                self,
                t("transcribe.file_req_title", "Falta el archivo"),
                t(
                    "transcribe.file_req_desc",
                    "Elige un archivo de audio o vídeo para transcribir.",
                ),
            )
            return
        try:
            self.transcription_service.check_available("whisper")
        except TranscriptionError as exc:
            self._refresh_transcribe_availability()
            ThemedMessageBox.warning(
                self,
                t("transcribe.unavailable_title", "Transcripción no disponible"),
                str(exc),
            )
            return
        model = self.cb_transcribe_model.currentText()
        language = self.le_transcribe_lang.text().strip() or "auto"
        device = self.cb_transcribe_device.currentText()

        self.transcribe_cancelled = False
        self.transcribe_modal = ProgressModal(self)
        self.transcribe_modal.cancelled.connect(self._cancel_transcription)
        self.transcribe_modal.show()

        self.transcribe_worker = TranscribeWorker(
            service=self.transcription_service,
            media_path=self.current_media_path,
            model=model,
            language=language,
            device=device,
        )
        self.transcribe_worker.step_updated.connect(self._on_transcribe_step)
        self.transcribe_worker.completed.connect(self._on_transcribe_completed)
        self.transcribe_worker.failed.connect(self._on_transcribe_failed)
        self.transcribe_start_time = time.time()
        self.transcribe_worker.start()

    def _cancel_transcription(self):
        self.transcribe_cancelled = True
        worker = getattr(self, "transcribe_worker", None)
        if worker is not None and worker.isRunning():
            worker.cancel()

    def _on_transcribe_step(self, step_name: str, payload: object):
        modal = getattr(self, "transcribe_modal", None)
        if modal is None or not modal.isVisible():
            return
        if step_name == "transcribing" and isinstance(payload, dict):
            count = payload.get("segments", 0)
            ratio = payload.get("ratio")
            if isinstance(ratio, float):
                modal.update_step(
                    0,
                    done=False,
                    text_override=t(
                        "transcribe.progress_pct",
                        "Transcribiendo… {count} segmentos ({pct}%)",
                        count=count,
                        pct=int(ratio * 100),
                    ),
                )
                modal.set_progress(ratio)
            else:
                elapsed = time.time() - getattr(
                    self, "transcribe_start_time", time.time()
                )
                modal.update_step(
                    0,
                    done=False,
                    text_override=t(
                        "transcribe.progress_count",
                        "Transcribiendo… {count} segmentos ({secs}s)",
                        count=count,
                        secs=int(elapsed),
                    ),
                )
                modal.set_progress(0.5)

    def _on_transcribe_completed(self, result):
        modal = getattr(self, "transcribe_modal", None)
        if modal is not None and modal.isVisible():
            modal.accept()
        if self.transcribe_cancelled:
            return
        output_format = (
            "vtt" if self.cb_transcribe_format.currentIndex() == 1 else "srt"
        )
        try:
            content = self.transcription_service.render(result, output_format)
        except TranscriptionError as exc:
            logger.warning(
                "No se pudo renderizar la transcripción (%s)", type(exc).__name__
            )
            ThemedMessageBox.critical(
                self,
                t("transcribe.render_error_title"),
                t("transcribe.error_generic"),
            )
            return
        base, _ = os.path.splitext(self.current_media_path or "transcription")
        out_path = f"{base}_transcribed.{output_format}"
        try:
            self.subtitle_service.write_output_file(out_path, content)
            self.saved_output_path = out_path
        except Exception:
            logger.exception("No se pudo guardar la transcripción")
            ThemedMessageBox.critical(
                self,
                t("alert.save_error_title"),
                t("alert.save_error_desc", err="error de escritura"),
            )
            return
        self.last_result = None
        items = self.transcription_service.to_subtitle_items(result)
        self.video_player.set_subtitles(items)
        self.card_lines.set_value(str(len(items)))
        self.card_deleted.set_value(result.language or "auto")
        elapsed = time.time() - getattr(self, "transcribe_start_time", time.time())
        m, s = int(elapsed // 60), int(elapsed % 60)
        self.card_time.set_value(f"{m:02d}:{s:02d}")
        self.lbl_sum3.setText(t("completed.saved_as", name=os.path.basename(out_path)))
        self._switch_page(6)
        try:
            from application.services.history_store import HistoryStore

            with HistoryStore() as store:
                store.record_transcription_result(
                    result,
                    file_path=self.current_media_path,
                    file_format=output_format,
                )
        except Exception as exc:
            logger.warning(
                "No se pudo registrar la transcripción (%s)", type(exc).__name__
            )

    def _on_transcribe_failed(self, error_msg: str):
        logger.error("Transcripción fallida")
        modal = getattr(self, "transcribe_modal", None)
        if modal is not None and modal.isVisible():
            modal.reject()
        if self.transcribe_cancelled:
            return
        ThemedMessageBox.critical(
            self,
            t("transcribe.error_title"),
            t("transcribe.error_generic"),
        )

    # ------------------ PÁGINA: PIPELINE ------------------
    def _build_pipeline_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        container = QWidget()
        container.setMaximumWidth(1020)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        self.lbl_pipeline_title = QLabel(t("pipeline.title", "Pipeline audiovisual"))
        self.lbl_pipeline_title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_pipeline_sub = QLabel(
            t(
                "pipeline.subtitle",
                "Transcripción → limpieza → analytics → QA → traducción "
                "opcional → QA final → exportación → burn-in opcional.",
            )
        )
        self.lbl_pipeline_sub.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_pipeline_sub.setWordWrap(True)
        layout.addWidget(self.lbl_pipeline_title)
        layout.addWidget(self.lbl_pipeline_sub)

        file_card = QFrame()
        file_card.setObjectName("CardContainer")
        f_layout = QHBoxLayout(file_card)
        f_layout.setContentsMargins(18, 14, 18, 14)
        self.lbl_pipeline_file = QLabel(
            t("pipeline.no_file", "Ningún archivo seleccionado")
        )
        self.lbl_pipeline_file.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED};"
        )
        f_layout.addWidget(self.lbl_pipeline_file, stretch=1)
        self.btn_choose_pipeline = QPushButton(
            t("pipeline.btn_choose", "Elegir archivo")
        )
        self.btn_choose_pipeline.setProperty("class", "secondary-btn")
        self.btn_choose_pipeline.setIcon(
            Icons.get_icon(
                "folder",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=16,
            )
        )
        self.btn_choose_pipeline.clicked.connect(self._choose_pipeline_file)
        f_layout.addWidget(self.btn_choose_pipeline)
        layout.addWidget(file_card)

        opts_card = QFrame()
        opts_card.setObjectName("CardContainer")
        o_layout = QGridLayout(opts_card)
        o_layout.setContentsMargins(18, 14, 18, 14)
        o_layout.setHorizontalSpacing(12)
        o_layout.setVerticalSpacing(10)
        self.lbl_pipeline_model = QLabel(t("pipeline.model", "Modelo Whisper"))
        self.cb_pipeline_model = QComboBox()
        self.cb_pipeline_model.addItems(
            ["tiny", "base", "small", "medium", "large-v3", "turbo"]
        )
        self.cb_pipeline_model.setCurrentText("small")
        self.lbl_pipeline_lang = QLabel(
            t("pipeline.language", "Idioma de origen (auto)")
        )
        self.le_pipeline_lang = QLineEdit("auto")
        self.le_pipeline_lang.setMaximumWidth(120)
        self.lbl_pipeline_target = QLabel(t("pipeline.target", "Idioma de destino"))
        self.le_pipeline_target = QLineEdit("en")
        self.le_pipeline_target.setMaximumWidth(120)
        self.lbl_pipeline_provider = QLabel(t("pipeline.provider", "Provider"))
        self.cb_pipeline_provider = QComboBox()
        self.cb_pipeline_provider.addItems(
            ["google", "deepl", "openai", "ollama", "llm"]
        )
        self.lbl_pipeline_format = QLabel(t("pipeline.format", "Formato"))
        self.cb_pipeline_format = QComboBox()
        self.cb_pipeline_format.addItems(["SRT (.srt)", "VTT (.vtt)"])
        o_layout.addWidget(self.lbl_pipeline_model, 0, 0)
        o_layout.addWidget(self.cb_pipeline_model, 0, 1)
        o_layout.addWidget(self.lbl_pipeline_lang, 0, 2)
        o_layout.addWidget(self.le_pipeline_lang, 0, 3)
        o_layout.addWidget(self.lbl_pipeline_target, 1, 0)
        o_layout.addWidget(self.le_pipeline_target, 1, 1)
        o_layout.addWidget(self.lbl_pipeline_provider, 1, 2)
        o_layout.addWidget(self.cb_pipeline_provider, 1, 3)
        o_layout.addWidget(self.lbl_pipeline_format, 2, 0)
        o_layout.addWidget(self.cb_pipeline_format, 2, 1)
        layout.addWidget(opts_card)

        stages_card = QFrame()
        stages_card.setObjectName("CardContainer")
        s_layout = QGridLayout(stages_card)
        s_layout.setContentsMargins(18, 14, 18, 14)
        s_layout.setHorizontalSpacing(12)
        s_layout.setVerticalSpacing(10)
        self.lbl_pipeline_clean = QLabel(t("pipeline.clean", "Limpieza"))
        self.toggle_pipeline_clean = ModernToggle(checked=True)
        self.lbl_pipeline_translate = QLabel(t("pipeline.translate", "Traducción"))
        self.toggle_pipeline_translate = ModernToggle(checked=False)
        self.lbl_pipeline_qa = QLabel(t("pipeline.qa", "QA"))
        self.toggle_pipeline_qa = ModernToggle(checked=True)
        self.lbl_pipeline_strict = QLabel(t("pipeline.strict", "QA estricto"))
        self.toggle_pipeline_strict = ModernToggle(checked=False)
        self.lbl_pipeline_burn = QLabel(t("pipeline.burn", "Burn-in"))
        self.toggle_pipeline_burn = ModernToggle(checked=False)
        s_layout.addWidget(self.lbl_pipeline_clean, 0, 0)
        s_layout.addWidget(self.toggle_pipeline_clean, 0, 1)
        s_layout.addWidget(self.lbl_pipeline_translate, 0, 2)
        s_layout.addWidget(self.toggle_pipeline_translate, 0, 3)
        s_layout.addWidget(self.lbl_pipeline_qa, 1, 0)
        s_layout.addWidget(self.toggle_pipeline_qa, 1, 1)
        s_layout.addWidget(self.lbl_pipeline_strict, 1, 2)
        s_layout.addWidget(self.toggle_pipeline_strict, 1, 3)
        s_layout.addWidget(self.lbl_pipeline_burn, 2, 0)
        s_layout.addWidget(self.toggle_pipeline_burn, 2, 1)
        self.btn_choose_video_out = QPushButton(
            t("pipeline.btn_video_out", "Vídeo salida…")
        )
        self.btn_choose_video_out.setProperty("class", "secondary-btn")
        self.btn_choose_video_out.clicked.connect(self._choose_pipeline_video_out)
        s_layout.addWidget(self.btn_choose_video_out, 2, 2, 1, 2)
        layout.addWidget(stages_card)

        self.btn_start_pipeline = QPushButton(
            t("pipeline.btn_start", "Ejecutar pipeline")
        )
        self.btn_start_pipeline.setObjectName("PrimaryBtn")
        self.btn_start_pipeline.setIcon(
            Icons.get_icon(
                "zap", normal_color="#FFFFFF", active_color="#FFFFFF", size=16
            )
        )
        self.btn_start_pipeline.setMinimumHeight(46)
        self.btn_start_pipeline.clicked.connect(self._start_pipeline)
        layout.addWidget(self.btn_start_pipeline)

        layout.addStretch()
        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    def _choose_pipeline_file(self):
        chosen = ask_open_file(
            self,
            t("pipeline.choose_title", "Elegir audio, vídeo o subtítulo"),
            self._pipeline_media_filter(),
        )
        if chosen:
            self.pipeline_input_path = chosen
            self.lbl_pipeline_file.setText(os.path.basename(chosen))

    def _pipeline_media_filter(self) -> str:
        from ..services.media_pipeline import MEDIA_EXTENSIONS, SUBTITLE_EXTENSIONS

        patterns = " ".join(
            f"*{ext}" for ext in sorted(MEDIA_EXTENSIONS | SUBTITLE_EXTENSIONS)
        )
        return (
            f"{t('pipeline.media_filter', patterns=patterns)};;{t('dialog.all_files')}"
        )

    def _choose_pipeline_video_out(self):
        chosen = ask_save_file(
            self,
            t("pipeline.video_out_title", "Vídeo de salida"),
            f"{t('pipeline.video_out_filter')};;{t('dialog.all_files')}",
        )
        if chosen:
            self.pipeline_video_output = chosen

    def _start_pipeline(self):
        # D6: one pipeline at a time (same re-entrancy contract as the other
        # start handlers).
        worker = getattr(self, "pipeline_worker", None)
        if worker is not None and worker.isRunning():
            return
        if not self.pipeline_input_path or not os.path.exists(self.pipeline_input_path):
            ThemedMessageBox.warning(
                self,
                t("pipeline.file_req_title", "Falta el archivo"),
                t(
                    "pipeline.file_req_desc",
                    "Elige un archivo de audio, vídeo o subtítulo.",
                ),
            )
            return
        do_translate = self.toggle_pipeline_translate.isChecked()
        target = self.le_pipeline_target.text().strip()
        if do_translate and not target:
            ThemedMessageBox.warning(
                self,
                t("pipeline.target_req_title", "Falta el destino"),
                t(
                    "pipeline.target_req_desc",
                    "Indica el idioma de destino para traducir.",
                ),
            )
            return
        do_burn = self.toggle_pipeline_burn.isChecked()
        if do_burn and not self.pipeline_video_output:
            ThemedMessageBox.warning(
                self,
                t("pipeline.video_req_title", "Falta el vídeo de salida"),
                t(
                    "pipeline.video_req_desc",
                    "Elige el archivo de vídeo de salida para el burn-in.",
                ),
            )
            return
        output_format = "vtt" if self.cb_pipeline_format.currentIndex() == 1 else "srt"
        try:
            config = PipelineConfig(
                input_media=self.pipeline_input_path,
                transcription_model=self.cb_pipeline_model.currentText(),
                transcription_language=self.le_pipeline_lang.text().strip() or "auto",
                clean_enabled=self.toggle_pipeline_clean.isChecked(),
                qa_enabled=self.toggle_pipeline_qa.isChecked(),
                qa_strict=self.toggle_pipeline_strict.isChecked(),
                translation_enabled=do_translate,
                target_language=target,
                provider=self.cb_pipeline_provider.currentText(),
                output_format=output_format,
                burn_in_enabled=do_burn,
                output_video=self.pipeline_video_output,
            ).validate()
        except PipelineConfigError as exc:
            ThemedMessageBox.warning(
                self,
                t("pipeline.config_title"),
                str(exc),
            )
            return

        self.pipeline_cancelled = False
        self.pipeline_modal = ProgressModal(self)
        self.pipeline_modal.cancelled.connect(self._cancel_pipeline)
        self.pipeline_modal.show()

        self.pipeline_worker = PipelineWorker(config)
        self.pipeline_worker.step_updated.connect(self._on_pipeline_step)
        self.pipeline_worker.completed.connect(self._on_pipeline_completed)
        self.pipeline_worker.failed.connect(self._on_pipeline_failed)
        self.pipeline_worker.start()

    def _cancel_pipeline(self):
        self.pipeline_cancelled = True
        worker = getattr(self, "pipeline_worker", None)
        if worker is not None and worker.isRunning():
            worker.cancel()

    def _on_pipeline_step(self, stage_name: str, payload: object):
        from ..services.media_pipeline import STAGE_ORDER

        modal = getattr(self, "pipeline_modal", None)
        if modal is None or not modal.isVisible():
            return
        total = len(STAGE_ORDER)
        try:
            position = STAGE_ORDER.index(stage_name)
        except ValueError:
            return
        intra = 0.0
        text = stage_name
        if isinstance(payload, dict):
            state = payload.get("state")
            if state == "ok":
                intra = 1.0
                text = f"{stage_name} ✓"
            elif state == "skipped":
                intra = 1.0
                text = f"{stage_name} (omitida)"
            else:
                ratio = payload.get("ratio")
                if isinstance(ratio, float):
                    intra = max(0.0, min(1.0, ratio))
                    text = f"{stage_name} ({int(intra * 100)}%)"
                elif isinstance(payload.get("segments"), int):
                    text = f"{stage_name} ({payload['segments']} seg.)"
        overall = min(1.0, (position + intra) / total)
        modal.update_step(position % 6, done=(intra == 1.0), text_override=text)
        modal.set_progress(overall)

    def _on_pipeline_completed(self, result):
        modal = getattr(self, "pipeline_modal", None)
        if modal is not None and modal.isVisible():
            modal.accept()
        if self.pipeline_cancelled:
            return
        if not result.success:
            errors = "; ".join(
                f"[{e['stage']}] {e['error_type']}" for e in result.errors
            )
            ThemedMessageBox.critical(
                self,
                t("pipeline.error_title"),
                errors or t("pipeline.error_unknown"),
            )
            return
        self.saved_output_path = result.output_subtitle
        cues = (
            (result.analytics_after or {}).get("content", {}).get("subtitle_count", 0)
        )
        self.card_lines.set_value(str(cues))
        self.card_deleted.set_value(str(result.cleaning.get("lines_removed", 0)))
        elapsed = result.total_duration_ms / 1000.0
        m, s = int(elapsed // 60), int(elapsed % 60)
        self.card_time.set_value(f"{m:02d}:{s:02d}")
        name = os.path.basename(result.output_subtitle or "")
        self.lbl_sum3.setText(t("completed.saved_as", name=name))
        self._switch_page(6)
        try:
            record_pipeline_result(
                result,
                self.pipeline_worker.config,
            )
        except Exception as exc:
            logger.warning("No se pudo registrar la pipeline (%s)", type(exc).__name__)

    def _on_pipeline_failed(self, error_msg: str):
        logger.error("Pipeline fallida")
        modal = getattr(self, "pipeline_modal", None)
        if modal is not None and modal.isVisible():
            modal.reject()
        if self.pipeline_cancelled:
            return
        ThemedMessageBox.critical(
            self,
            t("pipeline.error_title"),
            t("pipeline.error_desc", err=error_msg),
        )

    def _build_batch_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        container = QWidget()
        container.setMaximumWidth(1020)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        self.lbl_batch_title = QLabel(t("batch.title"))
        self.lbl_batch_title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_batch_sub = QLabel(t("batch.subtitle"))
        self.lbl_batch_sub.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_batch_sub.setWordWrap(True)
        layout.addWidget(self.lbl_batch_title)
        layout.addWidget(self.lbl_batch_sub)

        btn_layout = QHBoxLayout()
        self.btn_add_batch = QPushButton(t("batch.btn_add"))
        self.btn_add_batch.setProperty("class", "secondary-btn")
        self.btn_add_batch.setIcon(
            Icons.get_icon(
                "folder",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=16,
            )
        )
        self.btn_add_batch.clicked.connect(self._add_batch_files)

        self.btn_clear_batch = QPushButton(t("batch.btn_clear"))
        self.btn_clear_batch.setProperty("class", "secondary-btn")
        self.btn_clear_batch.setIcon(
            Icons.get_icon(
                "close",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=16,
            )
        )
        self.btn_clear_batch.clicked.connect(self._clear_batch_table)

        btn_layout.addWidget(self.btn_add_batch)
        btn_layout.addWidget(self.btn_clear_batch)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.batch_table = QTableWidget()
        self.batch_table.setColumnCount(4)
        self.batch_table.setHorizontalHeaderLabels(
            [
                t("batch.col_file"),
                t("batch.col_size"),
                t("batch.col_format"),
                t("batch.col_status"),
            ]
        )
        self.batch_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.batch_table.setMinimumHeight(240)
        layout.addWidget(self.batch_table)

        self.btn_start_batch = QPushButton(t("batch.btn_start"))
        self.btn_start_batch.setObjectName("PrimaryBtn")
        self.btn_start_batch.setIcon(
            Icons.get_icon(
                "zap", normal_color="#FFFFFF", active_color="#FFFFFF", size=16
            )
        )
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
        self.lbl_settings_title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {Styles.TEXT};"
        )
        layout.addWidget(self.lbl_settings_title)

        # 1. Interface Language Card
        lang_card = QFrame()
        lang_card.setObjectName("CardContainer")
        l_layout = QVBoxLayout(lang_card)
        l_layout.setContentsMargins(18, 16, 18, 16)
        l_layout.setSpacing(10)

        self.lbl_lang_card_title = QLabel(t("settings.lang_card_title"))
        self.lbl_lang_card_title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Styles.TEXT};"
        )
        self.lbl_lang_card_desc = QLabel(t("settings.lang_card_desc"))
        self.lbl_lang_card_desc.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_lang_card_desc.setWordWrap(True)
        l_layout.addWidget(self.lbl_lang_card_title)
        l_layout.addWidget(self.lbl_lang_card_desc)

        self.cb_settings_lang = QComboBox()
        self.cb_settings_lang.addItem(t("settings.lang_auto"), "auto")
        for code, meta in self.i18n.SUPPORTED_LANGUAGES.items():
            self.cb_settings_lang.addItem(meta["native"], code)
        cfg_lang = self.i18n.get_configured_language()
        s_idx = self.cb_settings_lang.findData(cfg_lang)
        if s_idx >= 0:
            self.cb_settings_lang.setCurrentIndex(s_idx)
        self.cb_settings_lang.currentIndexChanged.connect(
            self._on_settings_lang_changed
        )
        l_layout.addWidget(self.cb_settings_lang)

        # Aclara qué idioma se aplicará realmente: con "Automático (Sistema)" no
        # se veía si seguía al sistema o un idioma guardado de una sesión anterior.
        self.lbl_lang_effective = QLabel()
        self.lbl_lang_effective.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_lang_effective.setWordWrap(True)
        l_layout.addWidget(self.lbl_lang_effective)
        layout.addWidget(lang_card)

        # 2. DeepL Card
        deepl_card = QFrame()
        deepl_card.setObjectName("CardContainer")
        d_layout = QVBoxLayout(deepl_card)
        d_layout.setContentsMargins(18, 16, 18, 16)
        d_layout.setSpacing(10)

        self.lbl_deepl_title = QLabel(t("settings.deepl_title"))
        self.lbl_deepl_title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Styles.TEXT};"
        )
        self.lbl_deepl_desc = QLabel(t("settings.deepl_desc"))
        self.lbl_deepl_desc.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_deepl_desc.setWordWrap(True)
        d_layout.addWidget(self.lbl_deepl_title)
        d_layout.addWidget(self.lbl_deepl_desc)

        self.txt_deepl_key = QLineEdit()
        self.txt_deepl_key.setPlaceholderText(t("settings.deepl_placeholder"))
        d_layout.addWidget(self.txt_deepl_key)

        type_layout = QHBoxLayout()
        self.rb_deepl_free = QRadioButton(t("settings.deepl_free"))
        self.rb_deepl_pro = QRadioButton(t("settings.deepl_pro"))
        self.rb_deepl_free.setStyleSheet(f"color: {Styles.TEXT};")
        self.rb_deepl_pro.setStyleSheet(f"color: {Styles.TEXT};")
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
        self.lbl_openai_title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Styles.TEXT};"
        )
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
        self.btn_save_settings.setIcon(
            Icons.get_icon(
                "check", normal_color="#FFFFFF", active_color="#FFFFFF", size=16
            )
        )
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
        check_icon.setPixmap(
            Icons.get_pixmap("check", color=Icons.DEFAULT_SUCCESS, size=34)
        )

        text_layout = QVBoxLayout()
        self.lbl_completed_title = QLabel(t("completed.title"))
        self.lbl_completed_title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_completed_sub = QLabel(t("completed.subtitle"))
        self.lbl_completed_sub.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_completed_sub.setWordWrap(True)
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
        self.btn_open_file.setIcon(
            Icons.get_icon(
                "file", normal_color="#FFFFFF", active_color="#FFFFFF", size=16
            )
        )
        self.btn_open_file.clicked.connect(self._open_saved_file)

        self.btn_open_folder = QPushButton(t("completed.btn_open_folder"))
        self.btn_open_folder.setProperty("class", "secondary-btn")
        self.btn_open_folder.setIcon(
            Icons.get_icon(
                "folder",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=16,
            )
        )
        self.btn_open_folder.clicked.connect(self._open_output_folder)

        self.btn_to_preview = QPushButton(t("completed.btn_to_preview"))
        self.btn_to_preview.setProperty("class", "secondary-btn")
        self.btn_to_preview.setIcon(
            Icons.get_icon(
                "translate",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=16,
            )
        )
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
        self.lbl_summary_head.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Styles.TEXT};"
        )
        s_layout.addWidget(self.lbl_summary_head)

        self.lbl_sum1 = QLabel(t("completed.sum1"))
        self.lbl_sum2 = QLabel(t("completed.sum2"))
        self.lbl_sum3 = QLabel(t("completed.sum3"))
        for lbl in [self.lbl_sum1, self.lbl_sum2, self.lbl_sum3]:
            lbl.setStyleSheet(
                f"font-size: 13px; color: {Styles.SUCCESS}; font-weight: 500;"
            )
            s_layout.addWidget(lbl)

        layout.addWidget(summary_card)
        layout.addStretch()
        page_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    # ------------------ ACCIONES Y FLUJO ------------------
    def _on_file_selected(self, subtitle_path: str, video_path: str):
        # El DropZone ya guarda su propio `current_video_path`; MainWindow solo
        # necesita el subtítulo (el vídeo vive en `self.video_player`).
        self.current_subtitle_path = subtitle_path

        if video_path and os.path.exists(video_path):
            self.video_player.load_video(video_path)

    def _start_processing(self):
        # D6: one process job at a time. A second start while the previous
        # worker runs used to replace ``self.worker`` and run concurrently
        # against the same stateful ``SubtitleService``.
        worker = getattr(self, "worker", None)
        if worker is not None and worker.isRunning():
            return
        if not self.current_subtitle_path or not os.path.exists(
            self.current_subtitle_path
        ):
            ThemedMessageBox.warning(
                self, t("alert.file_req_title"), t("alert.file_req_desc")
            )
            return

        self._persist_home_options()
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
        self.worker.cancelled.connect(self._on_processing_cancelled)
        self.start_process_time = time.time()
        self.worker.start()

    def _cancel_worker(self):
        worker = getattr(self, "worker", None)
        if worker is not None and worker.isRunning() and hasattr(worker, "cancel"):
            worker.cancel()

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
            self.modal.update_step(
                3,
                done=(completed == total),
                text_override=t(
                    "progress.translating_progress", done=completed, total=total
                ),
            )
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
            # Deep-audit L9: write atomically so a failure never destroys the
            # user's previous good file.
            self.subtitle_service.write_output_file(out_path, result.output_content)
            self.saved_output_path = out_path
        except Exception:
            logger.exception("No se pudo guardar el resultado procesado")
            ThemedMessageBox.critical(
                self,
                t("alert.save_error_title"),
                t("alert.save_error_desc", err="error de escritura"),
            )
            return

        self.diff_viewer.load_subtitles(result.original_items, result.processed_items)
        self.video_player.set_subtitles(result.processed_items)

        self.card_lines.set_value(str(result.stats.total_lines))
        self.card_deleted.set_value(str(result.stats.deleted_lines))
        m = int(result.stats.elapsed_time // 60)
        s = int(result.stats.elapsed_time % 60)
        self.card_time.set_value(f"{m:02d}:{s:02d}")
        self.lbl_sum3.setText(t("completed.saved_as", name=os.path.basename(out_path)))

        self._switch_page(6)

        from application.services.history_store import record_result_safely

        worker = getattr(self, "worker", None)
        record_result_safely(
            result,
            operation="process",
            file_path=getattr(worker, "file_path", self.current_subtitle_path),
            file_format=getattr(worker, "target_format", None),
            source_language=getattr(worker, "source_lang", None),
            target_language=getattr(worker, "target_lang", None),
            engine=getattr(worker, "engine", None),
        )

        failures = result.stats.translation_failures
        if failures:
            logger.warning(
                "Traducción incompleta: %s de %s bloques mantienen el texto original",
                failures,
                len(result.processed_items),
            )
            ThemedMessageBox.warning(
                self,
                t("alert.translation_failures_title"),
                t(
                    "alert.translation_failures_desc",
                    failed=failures,
                    total=len(result.processed_items),
                ),
            )

        # P1: blocks the parser could not use are surfaced, never silently
        # dropped; the output is still delivered (advisory, not failure).
        parse_issues = list(getattr(result, "parse_issues", []) or [])
        if parse_issues:
            kinds = ", ".join(sorted({issue.kind for issue in parse_issues}))
            logger.warning(
                "El parser no pudo usar %s bloque(s): %s",
                len(parse_issues),
                kinds,
            )
            ThemedMessageBox.warning(
                self,
                t("alert.parse_issues_title"),
                t(
                    "alert.parse_issues_desc",
                    count=len(parse_issues),
                    kinds=kinds,
                ),
            )

    def _on_processing_failed(self, error_msg: str):
        logger.error("Procesamiento fallido")
        if hasattr(self, "modal") and self.modal.isVisible():
            self.modal.reject()
        ThemedMessageBox.critical(
            self,
            t("alert.process_error_title"),
            t("alert.process_error_desc", err="error interno"),
        )

    def _on_processing_cancelled(self):
        """The user cancelled: close the modal, publish nothing."""
        logger.info("Procesamiento cancelado por el usuario")
        modal = getattr(self, "modal", None)
        if modal is not None and modal.isVisible():
            modal.reject()

    def _start_fast_clean(self):
        # D6: same re-entrancy guard as _start_processing (shared worker
        # attribute and shared service instance).
        worker = getattr(self, "worker", None)
        if worker is not None and worker.isRunning():
            return
        if not self.current_subtitle_path:
            ThemedMessageBox.warning(
                self, t("alert.file_req_title"), t("alert.file_req_desc")
            )
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
        if not self.current_subtitle_path or not os.path.exists(
            self.current_subtitle_path
        ):
            ThemedMessageBox.warning(
                self, t("alert.file_req_title"), t("alert.file_req_convert_desc")
            )
            return

        fmt_map = {
            "SRT (.srt)": "srt",
            "VTT (.vtt)": "vtt",
            "ASS (.ass)": "ass",
            "TXT (.txt)": "txt",
        }
        tgt_fmt = fmt_map.get(self.cb_convert_format.currentText(), "srt")

        base, _ = os.path.splitext(self.current_subtitle_path)
        out_path = f"{base}_converted.{tgt_fmt}"

        try:
            with open(
                self.current_subtitle_path, "r", encoding="utf-8", errors="replace"
            ) as f:
                content = f.read()
            src_fmt = self.subtitle_service.detect_format(
                content, self.current_subtitle_path
            )
            items = self.subtitle_service.parse_subtitles(content, src_fmt)
            out_content = self.subtitle_service.format_output(items, tgt_fmt)

            self.subtitle_service.write_output_file(out_path, out_content)

            self.saved_output_path = out_path
            ThemedMessageBox.information(
                self,
                t("alert.conv_success_title"),
                t("alert.conv_success_desc", path=out_path),
            )
        except Exception:
            logger.exception("Falló la conversión del archivo")
            ThemedMessageBox.critical(
                self,
                t("alert.conv_error_title"),
                t("alert.conv_error_desc", err="error de conversión"),
            )

    def _on_subtitles_edited(self, edited_items):
        if self.last_result:
            self.last_result.processed_items = edited_items
        self.video_player.set_subtitles(edited_items)

    def _on_preview_search_changed(self, text: str):
        self.diff_viewer.filter_subtitles(text)

    def _on_preview_count_changed(self, visible: int, total: int):
        if total == 0:
            self.lbl_preview_sub_counter.setText(t("preview.sub_count_zero"))
        elif visible == total:
            self.lbl_preview_sub_counter.setText(
                t("preview.sub_count_all", total=total)
            )
        else:
            self.lbl_preview_sub_counter.setText(
                t("preview.sub_count_filtered", visible=visible, total=total)
            )

    def _on_video_position_sync(self, pos_ms: int):
        self.diff_viewer.highlight_cue_at_ms(
            pos_ms, auto_scroll=self.chk_autoscroll.isChecked()
        )

    def _export_result_file(self):
        items = self.diff_viewer.get_processed_subtitles()
        if not items and self.last_result:
            items = self.last_result.processed_items

        if not items:
            ThemedMessageBox.information(
                self, t("alert.info_title"), t("alert.nothing_save_desc")
            )
            return

        suggested_name = "subtitulo_editado.srt"
        if self.saved_output_path:
            suggested_name = self.saved_output_path
        elif self.current_subtitle_path:
            base, ext = os.path.splitext(self.current_subtitle_path)
            suggested_name = f"{base}_editado{ext}"

        path = ask_save_file(
            self,
            t("preview.save_dialog_title"),
            t("preview.save_filter"),
            suggested_name,
        )
        if path:
            ext = os.path.splitext(path)[1].lstrip(".")
            content = self.subtitle_service.format_output(items, ext)
            self.subtitle_service.write_output_file(path, content)
            self.saved_output_path = path
            ThemedMessageBox.information(
                self,
                t("alert.save_success_title"),
                t("alert.save_success_desc", path=path),
            )

    def _open_burn_in_dialog(self):
        items = self.diff_viewer.get_processed_subtitles()
        if not items and self.last_result:
            items = self.last_result.processed_items

        if not items:
            ThemedMessageBox.information(
                self, t("alert.no_subs_title"), t("alert.no_subs_desc")
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
            path = ask_open_file(
                self, t("burn.select_video_title"), t("preview.video_filter")
            )
            if not path:
                return
            video_path = path
            self.video_player.load_video(path)

        dialog = BurnInDialog(video_path=video_path, subtitle_items=items, parent=self)
        dialog.burn_requested.connect(self._start_burn_in_process)
        dialog.exec()

    def _start_burn_in_process(
        self, v_path: str, o_path: str, items: list, opts: BurnInOptions
    ):
        modal = BurnInProgressModal(v_path, o_path, items, opts, parent=self)
        modal.exec()

    def _browse_preview_file(self):
        path = ask_open_file(
            self, t("preview.select_subtitle_title"), t("preview.sub_filter")
        )
        if path:
            self.current_subtitle_path = path
            fmt = self.subtitle_service.detect_format("", path)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                items = self.subtitle_service.parse_subtitles(content, fmt)
                edited_items = copy.deepcopy(items)
                self.diff_viewer.load_subtitles(items, edited_items)
                self.video_player.set_subtitles(edited_items)
                matching_vid = self.drop_zone._find_matching_video(path)
                if matching_vid:
                    self.video_player.load_video(matching_vid)
            except Exception:
                logger.exception("No se pudo cargar el archivo de subtítulos")
                ThemedMessageBox.critical(
                    self,
                    t("alert.load_error_title"),
                    t("alert.load_error_desc", err="archivo ilegible"),
                )

    def _open_saved_file(self):
        if self.saved_output_path and os.path.exists(self.saved_output_path):
            open_path(self.saved_output_path)

    def _open_output_folder(self):
        if self.saved_output_path and os.path.exists(self.saved_output_path):
            reveal_path(self.saved_output_path)

    # ------------------ LOTE ------------------
    def _add_batch_files(self):
        files = ask_open_files(self, t("batch.title"), t("preview.sub_filter"))
        for f in files:
            row = self.batch_table.rowCount()
            self.batch_table.insertRow(row)
            self.batch_table.setItem(row, 0, QTableWidgetItem(f))
            size = (
                f"{os.path.getsize(f) / 1024:.1f} KB" if os.path.exists(f) else "0 KB"
            )
            self.batch_table.setItem(row, 1, QTableWidgetItem(size))
            ext = os.path.splitext(f)[1].upper().lstrip(".")
            self.batch_table.setItem(row, 2, QTableWidgetItem(ext))
            self.batch_table.setItem(row, 3, QTableWidgetItem(t("batch.status_queued")))

    def _clear_batch_table(self):
        self.batch_table.setRowCount(0)

    def _run_batch_processing(self):
        rows = self.batch_table.rowCount()
        if rows == 0:
            ThemedMessageBox.information(
                self, t("alert.batch_empty_title"), t("alert.batch_empty_desc")
            )
            return

        target_lang = self.cb_target_lang.currentData()
        source_lang = self.cb_source_lang.currentData()
        engine = self.cb_engine.currentData()
        do_translate = self.toggle_translate.isChecked()
        do_clean = self.toggle_clean.isChecked()
        parallel = self.toggle_parallel.isChecked()

        for row in range(rows):
            file_path = self.batch_table.item(row, 0).text()
            self.batch_table.setItem(
                row, 3, QTableWidgetItem(t("batch.status_processing"))
            )
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
                self.subtitle_service.write_output_file(out_path, result.output_content)
                self.batch_table.setItem(
                    row, 3, QTableWidgetItem(t("batch.status_completed"))
                )
                from application.services.history_store import record_result_safely

                record_result_safely(
                    result,
                    operation="process",
                    file_path=file_path,
                    source_language=source_lang,
                    target_language=target_lang,
                    engine=engine,
                )
            except Exception:
                logger.exception("Fallo al procesar el archivo del lote")
                self.batch_table.setItem(
                    row,
                    3,
                    QTableWidgetItem(t("batch.status_error", err="error interno")),
                )

        ThemedMessageBox.information(
            self, t("alert.batch_done_title"), t("alert.batch_done_desc")
        )

    # ------------------ AJUSTES ------------------
    def _load_config_values(self):
        self.txt_deepl_key.setText(self.config_service.get("deepl_api_key", ""))
        is_pro = self.config_service.get("deepl_type", "free") == "pro"
        self.rb_deepl_pro.setChecked(is_pro)
        self.rb_deepl_free.setChecked(not is_pro)

        self.txt_openai_key.setText(self.config_service.get("openai_api_key", ""))
        self.txt_openai_url.setText(
            self.config_service.get("openai_base_url", "https://api.openai.com/v1")
        )
        self.txt_openai_model.setText(
            self.config_service.get("openai_model", "gpt-4o-mini")
        )

        # Restaurar las opciones de la página de inicio
        self._select_combo_data(
            self.cb_source_lang, self.config_service.get("source_lang", "auto")
        )
        self._select_combo_data(
            self.cb_target_lang, self.config_service.get("target_lang", "es")
        )
        self._select_combo_data(
            self.cb_engine, self.config_service.get("preferred_engine", "google")
        )
        self.toggle_clean.setChecked(bool(self.config_service.get("auto_clean", True)))
        self.toggle_preserve.setChecked(
            bool(self.config_service.get("preserve_format", True))
        )

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: object) -> None:
        """Selecciona en un QComboBox el ítem cuyo data coincide con `value`, si existe."""
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _persist_home_options(self):
        """Guarda en disco las opciones de la página de inicio elegidas por el usuario."""
        saved = [
            self.config_service.set("source_lang", self.cb_source_lang.currentData()),
            self.config_service.set("target_lang", self.cb_target_lang.currentData()),
            self.config_service.set("preferred_engine", self.cb_engine.currentData()),
            self.config_service.set("auto_clean", self.toggle_clean.isChecked()),
            self.config_service.set(
                "preserve_format", self.toggle_preserve.isChecked()
            ),
        ]
        if not all(saved):
            # No se interrumpe el procesamiento por esto: sólo se registra.
            logger.warning(
                "No se pudieron guardar las opciones de la página de inicio (%s)",
                self.config_service.save_error,
            )

    def _save_settings(self):
        saved = [
            self.config_service.set("deepl_api_key", self.txt_deepl_key.text().strip()),
            self.config_service.set(
                "deepl_type", "pro" if self.rb_deepl_pro.isChecked() else "free"
            ),
            self.config_service.set(
                "openai_api_key", self.txt_openai_key.text().strip()
            ),
            self.config_service.set(
                "openai_base_url", self.txt_openai_url.text().strip()
            ),
            self.config_service.set(
                "openai_model", self.txt_openai_model.text().strip()
            ),
        ]
        if not all(saved):
            logger.error(
                "No se pudieron guardar los ajustes (%s)",
                self.config_service.save_error,
            )
            ThemedMessageBox.warning(
                self,
                t("alert.settings_save_error_title"),
                t(
                    "alert.settings_save_error_desc",
                    path=self.config_service.config_file,
                ),
            )
            return
        ThemedMessageBox.information(
            self, t("settings.save_success_title"), t("settings.save_success")
        )

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

    def _license_file_candidates(self) -> List[str]:
        """Rutas donde puede encontrarse el LICENSE (repo, bundle PyInstaller, cwd)."""
        repo_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        candidates = [
            os.path.join(repo_root, "LICENSE"),
            os.path.join(os.getcwd(), "LICENSE"),
        ]
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            candidates.insert(0, os.path.join(bundle_root, "LICENSE"))
        if getattr(sys, "frozen", False):
            candidates.insert(
                0, os.path.join(os.path.dirname(sys.executable), "LICENSE")
            )
        return candidates

    def _open_license_file(self):
        for lic_path in self._license_file_candidates():
            if os.path.exists(lic_path):
                open_path(lic_path)
                return
        QDesktopServices.openUrl(
            QUrl("https://creativecommons.org/licenses/by-nc-sa/4.0/")
        )

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(24, 18, 24, 18)
        page_layout.setSpacing(10)

        self.lbl_history_title = QLabel(t("history.title"))
        self.lbl_history_title.setStyleSheet(
            f"font-size: 20px; font-weight: 800; color: {Styles.TEXT};"
        )
        self.lbl_history_title.setWordWrap(True)
        self.lbl_history_sub = QLabel(t("history.subtitle"))
        self.lbl_history_sub.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_history_sub.setWordWrap(True)
        page_layout.addWidget(self.lbl_history_title)
        page_layout.addWidget(self.lbl_history_sub)

        self.btn_history_refresh = QPushButton(t("history.refresh"))
        self.btn_history_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_history_refresh.clicked.connect(self._refresh_history)
        page_layout.addWidget(
            self.btn_history_refresh, alignment=Qt.AlignmentFlag.AlignLeft
        )

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(8)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.history_table.verticalHeader().setVisible(False)
        page_layout.addWidget(self.history_table, stretch=1)

        self.lbl_history_empty = QLabel(t("history.empty"))
        self.lbl_history_empty.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_MUTED};"
        )
        self.lbl_history_empty.setWordWrap(True)
        page_layout.addWidget(self.lbl_history_empty)
        self._refresh_history()
        return page

    def _refresh_history(self) -> None:
        from application.services.history_store import HistoryError, HistoryStore

        headers = [
            t("history.col_time"),
            t("history.col_file"),
            t("history.col_operation"),
            t("history.col_provider"),
            t("history.col_duration"),
            t("history.col_status"),
            t("history.col_fallback"),
            t("history.col_parse_issues"),
        ]
        self.history_table.setHorizontalHeaderLabels(headers)
        try:
            with HistoryStore() as store:
                rows = store.recent_runs(limit=100)
        except HistoryError:
            rows = []
            logger.warning("Historial no disponible en la página History")
        self.history_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            timestamp = str(row.get("timestamp") or "")[:19].replace("T", " ")
            file_path = str(row.get("file_path") or row.get("benchmark_id") or "")
            duration = row.get("duration_ms")
            self.history_table.setItem(index, 0, QTableWidgetItem(timestamp))
            self.history_table.setItem(
                index, 1, QTableWidgetItem(os.path.basename(file_path) or file_path)
            )
            self.history_table.setItem(
                index, 2, QTableWidgetItem(str(row.get("operation") or ""))
            )
            self.history_table.setItem(
                index,
                3,
                QTableWidgetItem(
                    str(row.get("requested_provider") or row.get("provider") or "")
                ),
            )
            self.history_table.setItem(
                index,
                4,
                QTableWidgetItem(f"{duration} ms" if duration is not None else ""),
            )
            self.history_table.setItem(
                index,
                5,
                QTableWidgetItem(
                    "ok"
                    if row.get("success")
                    else str(row.get("error_type") or "error")
                ),
            )
            self.history_table.setItem(
                index,
                6,
                QTableWidgetItem("fallback" if row.get("fallback_used") else ""),
            )
            # P1: parsed-but-unusable block count is visible, not discarded.
            parse_issues = row.get("parse_issues")
            self.history_table.setItem(
                index,
                7,
                QTableWidgetItem(str(parse_issues) if parse_issues else ""),
            )
        self.lbl_history_empty.setVisible(not rows)

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
        self.lbl_about_title = QLabel(t("about.title"))
        self.lbl_about_title.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {Styles.TEXT};"
        )
        app_title = self.lbl_about_title

        tag_row = QHBoxLayout()
        tag_row.setSpacing(8)
        self.lbl_version_badge = QLabel(t("about.version_pill"))
        v_badge = self.lbl_version_badge
        v_badge.setStyleSheet(f"""
            background: #1E1B4B;
            color: {Styles.ACCENT_LIGHT};
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 4px;
            border: 1px solid #3730A3;
        """)
        v_status = QLabel(t("about.status"))
        v_status.setStyleSheet(f"font-size: 12px; color: {Styles.TEXT_MUTED};")
        self.lbl_about_status = v_status
        tag_row.addWidget(v_badge)
        tag_row.addWidget(v_status)
        tag_row.addStretch()

        app_desc = QLabel(t("about.desc"))
        app_desc.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_SUBTLE}; line-height: 1.4;"
        )
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
        dev_title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {Styles.TEXT};"
        )
        self.lbl_dev_title = dev_title
        d_layout.addWidget(dev_title)

        dev_name = QLabel(APP_AUTHOR_NAME)
        dev_name.setStyleSheet("font-size: 18px; font-weight: 800; color: #818CF8;")
        d_layout.addWidget(dev_name)

        self.lbl_dev_role = QLabel(
            f"{t('about.author_role')} · {t('about.author_location')}"
        )
        self.lbl_dev_role.setStyleSheet(
            "font-size: 12px; color: #818CF8; font-weight: 600;"
        )
        d_layout.addWidget(self.lbl_dev_role)

        self.lbl_dev_bio = QLabel(t("about.author_bio"))
        self.lbl_dev_bio.setStyleSheet(
            f"font-size: 13px; color: {Styles.TEXT_MUTED}; line-height: 1.4;"
        )
        self.lbl_dev_bio.setWordWrap(True)
        d_layout.addWidget(self.lbl_dev_bio)

        links_row = QHBoxLayout()
        links_row.setSpacing(12)

        btn_github = QPushButton(t("about.btn_profile") + f" (@{APP_GITHUB_OWNER})")
        btn_github.setStyleSheet(self._btn_link_style())
        btn_github.setIcon(
            Icons.get_icon(
                "external_link",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=14,
            )
        )
        btn_github.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_github.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(APP_GITHUB_PROFILE_URL))
        )
        self.btn_github = btn_github
        links_row.addWidget(btn_github)

        btn_repo = QPushButton(t("about.btn_repo") + " (SRT4U)")
        btn_repo.setStyleSheet(self._btn_link_style())
        btn_repo.setIcon(
            Icons.get_icon(
                "external_link",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=14,
            )
        )
        btn_repo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_repo.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(APP_GITHUB_REPO_URL))
        )
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
        lic_title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {Styles.TEXT};"
        )
        self.lbl_lic_title = lic_title
        l_layout.addWidget(lic_title)

        lic_badge_row = QHBoxLayout()
        lic_badge_row.setSpacing(10)
        lic_badge = QLabel("GPL-3.0-only")
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
        lic_name.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {Styles.TEXT};"
        )
        lic_name.setWordWrap(True)
        self.lbl_lic_name = lic_name
        lic_badge_row.addWidget(lic_badge)
        lic_badge_row.addWidget(lic_name, stretch=1)
        l_layout.addLayout(lic_badge_row)

        self.lbl_lic_para = QLabel(t("about.license_desc"))
        self.lbl_lic_para.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_SUBTLE}; line-height: 1.5;"
        )
        self.lbl_lic_para.setWordWrap(True)
        l_layout.addWidget(self.lbl_lic_para)

        lic_terms = QLabel(self._build_license_terms())
        lic_terms.setStyleSheet(
            f"font-size: 12px; color: {Styles.TEXT_SUBTLE}; line-height: 1.6;"
        )
        lic_terms.setTextFormat(Qt.TextFormat.RichText)
        lic_terms.setWordWrap(True)
        self.lbl_lic_desc = lic_terms
        l_layout.addWidget(lic_terms)

        lic_btn_row = QHBoxLayout()
        lic_btn_row.setSpacing(12)
        btn_view_lic = QPushButton(t("about.btn_open_license"))
        btn_view_lic.setStyleSheet(self._btn_link_style())
        btn_view_lic.setIcon(
            Icons.get_icon(
                "file",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=14,
            )
        )
        btn_view_lic.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_view_lic.clicked.connect(self._open_license_file)
        self.btn_open_license = btn_view_lic
        lic_btn_row.addWidget(btn_view_lic)

        btn_cc_web = QPushButton(t("about.btn_web_deed"))
        btn_cc_web.setStyleSheet(self._btn_link_style())
        btn_cc_web.setIcon(
            Icons.get_icon(
                "globe",
                normal_color=Icons.DEFAULT_MUTED,
                active_color="#FFFFFF",
                size=14,
            )
        )
        btn_cc_web.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cc_web.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://www.gnu.org/licenses/gpl-3.0.html")
            )
        )
        self.btn_web_deed = btn_cc_web
        lic_btn_row.addWidget(btn_cc_web)

        lic_btn_row.addStretch()
        l_layout.addLayout(lic_btn_row)

        layout.addWidget(lic_card)
        layout.addStretch()

        scroll.setWidget(container)
        page_layout.addWidget(scroll)
        return page

    @staticmethod
    def _build_license_terms() -> str:
        return (
            f"• <b>{t('about.perm_title')}:</b><br>"
            f"• {t('about.perm_1')}<br>"
            f"• {t('about.perm_2')}<br>"
            f"• {t('about.perm_3')}<br>"
            f"• <b>{t('about.restr_title')}:</b><br>"
            f"• {t('about.restr_1')}<br>"
            f"• {t('about.restr_2')}<br>"
            f"• {t('about.restr_3')}"
        )

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
            self._refresh_effective_language()

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
            self._refresh_effective_language()

    def _refresh_effective_language(self):
        """
        Muestra qué idioma está en vigor realmente.

        "Automático (Sistema)" es ambiguo: con él la app sigue al idioma del
        sistema, pero si el usuario eligió antes un idioma concreto, ése es el
        guardado en la configuración. Aquí se aclara la diferencia.
        """
        configured = self.i18n.get_configured_language()
        if configured == "auto":
            code = self.i18n.detect_system_language()
            key = "settings.lang_effective_auto"
        else:
            code = configured if configured in self.i18n.SUPPORTED_LANGUAGES else "en"
            key = "settings.lang_effective"
        language = self.i18n.SUPPORTED_LANGUAGES.get(code, {}).get("native", code)

        if hasattr(self, "lbl_lang_effective"):
            self.lbl_lang_effective.setText(t(key, language=language))
        if hasattr(self, "cb_top_lang"):
            tooltip_key = (
                "topbar.lang_tooltip_effective" if configured == "auto" else None
            )
            if tooltip_key:
                self.cb_top_lang.setToolTip(t(tooltip_key, language=language))
            else:
                self.cb_top_lang.setToolTip(t("topbar.lang_tooltip"))

    def retranslate_ui(self):
        # 0. Global chrome
        self.setWindowTitle(t("about.title"))
        if hasattr(self, "lbl_app_sub"):
            self.lbl_app_sub.setText(t("app.subtitle"))
        if hasattr(self, "btn_theme"):
            self.btn_theme.setToolTip(t("topbar.theme_tooltip"))
            self.btn_theme.setAccessibleName(t("topbar.theme_tooltip"))
        if hasattr(self, "cb_source_lang"):
            self.cb_source_lang.setItemText(0, t("home.lang_auto"))
        if hasattr(self, "cb_engine"):
            self.cb_engine.setItemText(0, t("home.engine_deepl"))
            self.cb_engine.setItemText(1, t("home.engine_google"))
            self.cb_engine.setItemText(2, t("home.engine_openai"))
        if hasattr(self, "cb_top_lang"):
            self.cb_top_lang.setItemText(0, t("topbar.lang_auto"))
        if hasattr(self, "cb_settings_lang"):
            self.cb_settings_lang.setItemText(0, t("settings.lang_auto"))
        self._refresh_effective_language()

        # 1. Sidebar Nav
        for btn in self.nav_buttons:
            key = btn.property("i18n_key")
            if key:
                btn.setText(_nav_label(key))

        # 2. Home Page
        if hasattr(self, "lbl_home_title"):
            self.lbl_home_title.setText(t("home.title"))
            self.lbl_home_sub.setText(t("home.subtitle"))
            self.lbl_src_lang.setText(t("home.source_lang"))
            self.lbl_tgt_lang.setText(t("home.target_lang"))
            self.lbl_engine.setText(t("home.engine"))
            self.card_translate.set_texts(
                t("home.translate_title"), t("home.translate_desc")
            )
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
            self.preview_search_input.setPlaceholderText(
                t("preview.search_placeholder")
            )
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

        # 5b. Transcribe Page
        if hasattr(self, "lbl_transcribe_title"):
            self.lbl_transcribe_title.setText(
                t("transcribe.title", "Transcribir multimedia")
            )
            self.lbl_transcribe_sub.setText(
                t(
                    "transcribe.subtitle",
                    "Convierte audio o vídeo en subtítulos con Whisper local. "
                    "El resultado alimenta Analytics, QA, limpieza y traducción.",
                )
            )
            if not getattr(self, "current_media_path", None):
                self.lbl_transcribe_file.setText(
                    t("transcribe.no_file", "Ningún archivo seleccionado")
                )
            self.lbl_transcribe_model.setText(t("transcribe.model", "Modelo Whisper"))
            self.lbl_transcribe_lang.setText(
                t("transcribe.language", "Idioma de origen (auto)")
            )
            self.lbl_transcribe_format.setText(t("transcribe.format", "Formato"))
            self.lbl_transcribe_device.setText(t("transcribe.device", "Dispositivo"))
            self.btn_choose_media.setText(t("transcribe.btn_choose", "Elegir archivo"))
            self.btn_start_transcribe.setText(t("transcribe.btn_start", "Transcribir"))
            self._refresh_transcribe_availability()

        # 5c. Pipeline Page
        if hasattr(self, "lbl_pipeline_title"):
            self.lbl_pipeline_title.setText(t("pipeline.title", "Pipeline audiovisual"))
            self.lbl_pipeline_sub.setText(
                t(
                    "pipeline.subtitle",
                    "Transcripción → limpieza → analytics → QA → traducción "
                    "opcional → QA final → exportación → burn-in opcional.",
                )
            )
            if not getattr(self, "pipeline_input_path", None):
                self.lbl_pipeline_file.setText(
                    t("pipeline.no_file", "Ningún archivo seleccionado")
                )
            self.lbl_pipeline_model.setText(t("pipeline.model", "Modelo Whisper"))
            self.lbl_pipeline_lang.setText(
                t("pipeline.language", "Idioma de origen (auto)")
            )
            self.lbl_pipeline_target.setText(t("pipeline.target", "Idioma de destino"))
            self.lbl_pipeline_provider.setText(t("pipeline.provider", "Provider"))
            self.lbl_pipeline_format.setText(t("pipeline.format", "Formato"))
            self.lbl_pipeline_clean.setText(t("pipeline.clean", "Limpieza"))
            self.lbl_pipeline_translate.setText(t("pipeline.translate", "Traducción"))
            self.lbl_pipeline_qa.setText(t("pipeline.qa", "QA"))
            self.lbl_pipeline_strict.setText(t("pipeline.strict", "QA estricto"))
            self.lbl_pipeline_burn.setText(t("pipeline.burn", "Burn-in"))
            self.btn_choose_pipeline.setText(t("pipeline.btn_choose", "Elegir archivo"))
            self.btn_choose_video_out.setText(
                t("pipeline.btn_video_out", "Vídeo de salida…")
            )
            self.btn_start_pipeline.setText(
                t("pipeline.btn_start", "Ejecutar pipeline")
            )

        # 6. Batch Page
        if hasattr(self, "lbl_batch_title"):
            self.lbl_batch_title.setText(t("batch.title"))
            self.lbl_batch_sub.setText(t("batch.subtitle"))
            self.btn_add_batch.setText(t("batch.btn_add"))
            self.btn_clear_batch.setText(t("batch.btn_clear"))
            self.batch_table.setHorizontalHeaderLabels(
                [
                    t("batch.col_file"),
                    t("batch.col_size"),
                    t("batch.col_format"),
                    t("batch.col_status"),
                ]
            )
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
            self.txt_openai_model.setPlaceholderText(
                t("settings.openai_model_placeholder")
            )
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
            self.lbl_about_title.setText(t("about.title"))
            self.lbl_version_badge.setText(t("about.version_pill"))
            self.lbl_about_status.setText(t("about.status"))
            self.lbl_about_desc.setText(t("about.desc"))
            self.lbl_dev_title.setText(t("about.author_title"))
            self.lbl_dev_role.setText(
                f"{t('about.author_role')} · {t('about.author_location')}"
            )
            self.lbl_dev_bio.setText(t("about.author_bio"))
            self.btn_github.setText(t("about.btn_profile") + " (@marodriguezd)")
            self.btn_repo.setText(t("about.btn_repo") + " (SRT4U)")
            self.lbl_lic_title.setText(t("about.license_title"))
            self.lbl_lic_name.setText(t("about.license_name"))
            self.lbl_lic_para.setText(t("about.license_desc"))
            self.lbl_lic_desc.setText(self._build_license_terms())
            self.btn_open_license.setText(t("about.btn_open_license"))
            self.btn_web_deed.setText(t("about.btn_web_deed"))

        # 10. History Page
        if hasattr(self, "lbl_history_title"):
            self.lbl_history_title.setText(t("history.title"))
            self.lbl_history_sub.setText(t("history.subtitle"))
            self.btn_history_refresh.setText(t("history.refresh"))
            self.lbl_history_empty.setText(t("history.empty"))
            self._refresh_history()

        # Reaplica el tinte de tema por si alguna vista redefinió colores inline al retraducir
        Styles.retint_inline_text(self.central_widget, self.dark_mode)
