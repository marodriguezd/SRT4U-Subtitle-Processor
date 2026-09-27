"""
Utilidad de desarrollo: regenera las capturas de verificación visual de la UI
en /tmp/srt4u-shots (ventana principal × páginas/idiomas/temas y los diálogos
de burn-in, progreso, archivos y mensajes × idiomas).

Uso:
    .venv/bin/python tools/regenerate_screenshots.py [--out DIR] [--langs en,es,...]

Requiere PyQt6. Si no hay display disponible, fuerza la plataforma offscreen.
"""

import argparse
import os
import sys

# Permite ejecutar el script desde el raíz del repo sin instalación.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from application.services.config_service import ConfigService  # noqa: E402
from application.services.i18n_service import get_i18n, t  # noqa: E402
from application.services.subtitle_service import SubtitleItem  # noqa: E402
from application.ui.burn_in_dialog import (  # noqa: E402
    BurnInDialog,
    BurnInOptions,
    BurnInProgressModal,
)
from application.ui.file_dialogs import prepare_dialog  # noqa: E402
from application.ui.main_window import MainWindow  # noqa: E402
from application.ui.message_boxes import ThemedMessageBox  # noqa: E402
from application.ui.styles import Styles  # noqa: E402
from application.ui.widgets import ProgressModal  # noqa: E402

WINDOW_PAGES = [(0, "home"), (5, "settings"), (7, "about")]
WINDOW_LANGS = ["en", "de", "pt"]
DIALOG_LANGS = ["en", "es", "pt", "de", "it", "zh-CN"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenera las capturas de UI de SRT4U."
    )
    parser.add_argument(
        "--out", default="/tmp/srt4u-shots", help="Directorio de salida"
    )
    parser.add_argument(
        "--langs",
        default=",".join(DIALOG_LANGS),
        help="Idiomas para los diálogos (coma-separados)",
    )
    return parser.parse_args()


def _save(widget, path: str) -> None:
    widget.grab().save(path)


def _shoot_system_dialogs(app, args, langs) -> None:
    """Captura el diálogo de archivos (claro/oscuro) y un message box por idioma."""
    for lang in langs:
        get_i18n().set_language(lang, save_to_config=False)

        for dark in (True, False):
            theme = "dark" if dark else "light"
            dialog = prepare_dialog(
                QFileDialog(
                    None,
                    t("dropzone.dialog_title"),
                    os.path.expanduser("~"),
                    t("dropzone.filter"),
                ),
                dark=dark,
            )
            dialog.show()
            app.processEvents()
            _save(dialog, os.path.join(args.out, f"filedialog_{lang}_{theme}.png"))
            print(
                f"filedialog_{lang}_{theme}: {dialog.width()}x{dialog.height()} "
                f"({len(dialog.styleSheet())} chars QSS)"
            )
            dialog.close()

        Styles.set_dark(True)
        box = ThemedMessageBox.build(
            QMessageBox.Icon.Warning,
            None,
            t("alert.file_req_title"),
            t("alert.file_req_desc"),
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )
        box.show()
        app.processEvents()
        _save(box, os.path.join(args.out, f"messagebox_{lang}.png"))
        print(f"messagebox_{lang}: {box.width()}x{box.height()}")
        box.close()


def main() -> int:
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)
    for stale in os.listdir(args.out):
        if stale.endswith(".png"):
            os.remove(os.path.join(args.out, stale))

    app = QApplication.instance() or QApplication([])
    i18n = get_i18n(ConfigService())
    items = [SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hello world")]

    # --- Ventana principal: páginas × idiomas × temas ---
    for lang in WINDOW_LANGS:
        i18n.set_language(lang, save_to_config=False)
        for dark in (True, False):
            win = MainWindow()
            win.dark_mode = dark
            win._apply_theme()
            win.retranslate_ui()
            win.show()
            app.processEvents()
            theme = "dark" if dark else "light"
            for page, name in WINDOW_PAGES:
                win._switch_page(page)
                app.processEvents()
                _save(win, os.path.join(args.out, f"{name}_{lang}_{theme}.png"))
            win.close()

    # --- Diálogo de burn-in (mínimo dinámico por idioma) ---
    dialog_langs = [lang.strip() for lang in args.langs.split(",") if lang.strip()]
    for lang in dialog_langs:
        i18n.set_language(lang, save_to_config=False)
        dialog = BurnInDialog(video_path="/tmp/movie.mp4", subtitle_items=items)
        dialog.show()
        app.processEvents()
        _save(dialog, os.path.join(args.out, f"burn_{lang}.png"))
        print(
            f"burn_{lang}: {dialog.width()}x{dialog.height()} "
            f"(min {dialog.minimumWidth()}x{dialog.minimumHeight()})"
        )
        dialog.close()

    # --- Modales de progreso (mínimo dinámico; sin FFmpeg real) ---
    BurnInProgressModal._start_worker = lambda self, *a, **k: None
    for lang in dialog_langs[:2]:
        i18n.set_language(lang, save_to_config=False)

        progress = ProgressModal()
        progress.show()
        app.processEvents()
        _save(progress, os.path.join(args.out, f"progress_{lang}.png"))
        print(f"progress_{lang}: {progress.width()}x{progress.height()}")
        progress.close()

        burn_modal = BurnInProgressModal(
            video_path="/tmp/movie.mp4",
            output_path="/tmp/out.mp4",
            subtitle_items=items,
            options=BurnInOptions(),
        )
        burn_modal.show()
        app.processEvents()
        _save(burn_modal, os.path.join(args.out, f"burnprogress_{lang}.png"))
        print(f"burnprogress_{lang}: {burn_modal.width()}x{burn_modal.height()}")
        burn_modal.close()

    # --- Diálogos del sistema (archivos y mensajes) ---
    _shoot_system_dialogs(app, args, dialog_langs)

    print(f"Capturas guardadas en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
