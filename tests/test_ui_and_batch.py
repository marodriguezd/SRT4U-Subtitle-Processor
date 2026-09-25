import os
import sys
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

QMessageBox.information = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.critical = lambda *args, **kwargs: QMessageBox.StandardButton.Ok

from application.ui.main_window import MainWindow
from application.ui.widgets import ModernToggle, CircularProgress, DropZone, SubtitleDiffViewer, SubtitleCard
from application.services.subtitle_service import SubtitleService, SubtitleItem

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_ui_components(qapp):
    toggle = ModernToggle(checked=False)
    assert not toggle.isChecked()
    toggle.setChecked(True)
    assert toggle.isChecked()

    circle = CircularProgress()
    circle.set_progress(0.75)
    assert circle.progress == 0.75

    drop = DropZone()
    path = os.path.join(FIXTURES_DIR, "sample.srt")
    drop.set_file(path)
    assert drop.current_subtitle_path == path


def test_main_window_flow(qapp, tmp_path):
    win = MainWindow()
    assert win.stack.count() == 7

    # Prueba de cambio de páginas
    win._switch_page(0)
    assert win.stack.currentIndex() == 0
    win._switch_page(3)  # Convertir
    assert win.stack.currentIndex() == 3

    # Carga de archivo
    sample_srt = os.path.join(FIXTURES_DIR, "sample.srt")
    win._on_file_selected(sample_srt, "")
    assert win.current_subtitle_path == sample_srt

    # Prueba de conversión directa en la vista
    win.cb_convert_format.setCurrentText("VTT (.vtt)")
    win._run_format_conversion()

    expected_converted = os.path.join(FIXTURES_DIR, "sample_converted.vtt")
    if os.path.exists(expected_converted):
        os.remove(expected_converted)


def test_batch_processing_logic(tmp_path):
    service = SubtitleService()
    files = [
        os.path.join(FIXTURES_DIR, "sample.srt"),
        os.path.join(FIXTURES_DIR, "sample.vtt"),
    ]

    for f in files:
        res = service.process_subtitles(
            file_path=f,
            do_clean=True,
            do_translate=False,
            target_language="es"
        )
        assert res.stats.total_lines > 0
        assert len(res.output_content) > 0


def test_subtitle_card_and_diff_viewer(qapp):
    orig = [
        SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="Hello world"),
        SubtitleItem(index=2, start_ms=4000, end_ms=7000, text="How are you?"),
    ]
    proc = [
        SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="Hola mundo"),
        SubtitleItem(index=2, start_ms=4000, end_ms=7000, text="¿Cómo estás?"),
    ]

    viewer = SubtitleDiffViewer()
    viewer.show()
    viewer.load_subtitles(orig, proc)
    assert len(viewer.cards) == 2
    assert viewer.cards[0].original_item.text == "Hello world"
    assert viewer.cards[0].edited_item.text == "Hola mundo"

    # Search filter
    vis, total = viewer.filter_subtitles("mundo")
    assert vis == 1
    assert total == 2
    assert not viewer.cards[0].isHidden()
    assert viewer.cards[1].isHidden()

    viewer.filter_subtitles("")
    assert not viewer.cards[0].isHidden()
    assert not viewer.cards[1].isHidden()

    # Active cue highlight
    viewer.highlight_cue_at_ms(2000, auto_scroll=False)
    assert viewer.cards[0].is_active is True
    assert viewer.cards[1].is_active is False

    viewer.highlight_cue_at_ms(5000, auto_scroll=False)
    assert viewer.cards[0].is_active is False
    assert viewer.cards[1].is_active is True

    # Edit text
    edited_events = []
    viewer.subtitles_edited.connect(lambda items: edited_events.append(items))
    viewer.cards[0].edit_text.setPlainText("Hola universo")
    assert len(edited_events) > 0
    assert viewer.get_processed_subtitles()[0].text == "Hola universo"


def test_preview_page_studio_integration(qapp):
    win = MainWindow()
    win._switch_page(1)  # Preview / Studio page
    assert win.stack.currentIndex() == 1
    assert win.video_player is not None
    assert win.diff_viewer is not None
    assert win.preview_search_input is not None
    assert win.chk_autoscroll.isChecked()

    sample_srt = os.path.join(FIXTURES_DIR, "sample.srt")
    with open(sample_srt, "r", encoding="utf-8") as f:
        items = win.subtitle_service.parse_subtitles(f.read(), "srt")
    import copy
    win.diff_viewer.load_subtitles(items, copy.deepcopy(items))
    assert len(win.diff_viewer.cards) > 0

    # Test search input
    win.preview_search_input.setText("xyz_not_found_token_999")
    assert win.lbl_preview_sub_counter.text().startswith("Mostrando 0")
    win.preview_search_input.setText("")
    assert "Total:" in win.lbl_preview_sub_counter.text()

