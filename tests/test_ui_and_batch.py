import copy
import os
import shutil

from application.ui.main_window import MainWindow
from application.ui.widgets import (
    ModernToggle,
    CircularProgress,
    DropZone,
    SubtitleDiffViewer,
)
from application.services.subtitle_service import SubtitleService, SubtitleItem

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_player_icon_only_controls_are_named(qapp):
    """Play/mute/sliders must expose tooltip + accessibleName (a11y)."""
    from application.services.i18n_service import t
    from application.ui.widgets import VideoPreviewPlayer

    player = VideoPreviewPlayer()
    for control in (
        player.play_btn,
        player.btn_mute,
        player.time_slider,
        player.vol_slider,
    ):
        assert control.toolTip().strip(), control
        assert control.accessibleName().strip(), control
    # Icon always mirrors the real playback state (starts stopped -> play).
    player._sync_play_icon()
    assert player.play_btn.toolTip() == t("preview.play_tooltip")
    assert player.play_btn.accessibleName() == t("preview.play_tooltip")


def test_player_controls_are_named_before_any_language_change(qapp):
    """Controls are named at construction, not only after `retranslate()`."""
    from application.services.i18n_service import t
    from application.ui.widgets import VideoPreviewPlayer

    player = VideoPreviewPlayer()
    assert player.btn_load_video.accessibleName() == t("preview.btn_load_video")
    assert player.time_slider.accessibleName() == t("preview.seek_tooltip")
    assert player.vol_slider.accessibleName() == t("preview.volume_tooltip")


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
    assert win.stack.count() == 11

    # Page switching check
    win._switch_page(0)
    assert win.stack.currentIndex() == 0
    win._switch_page(3)  # Convert
    assert win.stack.currentIndex() == 3
    win._switch_page(7)  # About
    assert win.stack.currentIndex() == 7
    win._switch_page(8)  # History
    assert win.stack.currentIndex() == 8
    win._switch_page(9)  # Transcribe
    assert win.stack.currentIndex() == 9
    win._switch_page(10)  # Pipeline
    assert win.stack.currentIndex() == 10

    # Conversion writes next to the source file: work on a temp copy
    # to keep tests/fixtures clean.
    sample_srt = str(tmp_path / "sample.srt")
    shutil.copyfile(os.path.join(FIXTURES_DIR, "sample.srt"), sample_srt)
    win._on_file_selected(sample_srt, "")
    assert win.current_subtitle_path == sample_srt

    # Direct in-view conversion check
    win.cb_convert_format.setCurrentText("VTT (.vtt)")
    win._run_format_conversion()

    expected_processed = str(tmp_path / "sample_processed.vtt")
    assert os.path.exists(expected_processed)
    assert os.path.getsize(expected_processed) > 0


def test_batch_processing_logic(tmp_path):
    service = SubtitleService()
    files = [
        os.path.join(FIXTURES_DIR, "sample.srt"),
        os.path.join(FIXTURES_DIR, "sample.vtt"),
    ]

    for f in files:
        res = service.process_subtitles(
            file_path=f, do_clean=True, do_translate=False, target_language="es"
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


def test_highlight_matches_first_cue_even_with_overlaps(qapp):
    """A4: the cached fast path must not change which cue wins.

    The reference is the original rule: the first cue in list order whose
    interval contains the position, even when cues overlap or are unsorted.
    """
    cues = [
        SubtitleItem(index=1, start_ms=0, end_ms=4000, text="long first"),
        SubtitleItem(index=2, start_ms=1000, end_ms=2000, text="overlap"),
        SubtitleItem(index=3, start_ms=500, end_ms=9000, text="late start"),
        SubtitleItem(index=4, start_ms=9500, end_ms=9900, text="tail"),
    ]
    viewer = SubtitleDiffViewer()
    viewer.show()
    viewer.load_subtitles(cues, list(cues))

    positions = [0, 600, 1200, 1500, 1999, 2000, 3000, 4001, 6000, 9001, 9600]
    for pos in positions + list(reversed(positions)):
        viewer.highlight_cue_at_ms(pos, auto_scroll=False)
        expected = next(
            (
                card
                for card in viewer.cards
                if card.edited_item.start_ms <= pos <= card.edited_item.end_ms
            ),
            None,
        )
        assert viewer.active_card is expected, pos


def test_preview_search_updates_counter_before_relayout(qapp):
    """A3: the counter is immediate; the visibility pass is debounced."""
    win = MainWindow()
    win.i18n.set_language("es", save_to_config=False)
    items = [
        SubtitleItem(index=1, start_ms=0, end_ms=1000, text="Hola mundo"),
        SubtitleItem(index=2, start_ms=2000, end_ms=3000, text="Adiós mundo"),
        SubtitleItem(index=3, start_ms=4000, end_ms=5000, text="Sin coincidencia"),
    ]
    win.diff_viewer.load_subtitles(items, copy.deepcopy(items))

    win.preview_search_input.setText("mundo")
    # Counter is already correct for the pending query...
    assert win.lbl_preview_sub_counter.text().startswith("Mostrando 2")
    # ...while no card has been hidden yet.
    assert all(not card.isHidden() for card in win.diff_viewer.cards)

    win._apply_preview_filter()
    assert [card.isHidden() for card in win.diff_viewer.cards] == [False, False, True]
    assert win.lbl_preview_sub_counter.text().startswith("Mostrando 2")
    win._search_timer.stop()
    win.close()


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
    win.diff_viewer.load_subtitles(items, copy.deepcopy(items))
    assert len(win.diff_viewer.cards) > 0

    # Test search input (pin the language to validate the translated text)
    win.i18n.set_language("es", save_to_config=False)
    win.preview_search_input.setText("xyz_not_found_token_999")
    assert win.lbl_preview_sub_counter.text().startswith("Mostrando 0")
    win.preview_search_input.setText("")
    assert "Total:" in win.lbl_preview_sub_counter.text()


def test_diff_viewer_materializes_only_the_visible_window(qapp):
    """B5: a long file must not build one widget tree per cue up front."""
    cues = [
        SubtitleItem(
            index=position + 1,
            start_ms=position * 2000,
            end_ms=position * 2000 + 1800,
            text=f"Cue {position}",
        )
        for position in range(600)
    ]
    viewer = SubtitleDiffViewer()
    viewer.resize(900, 600)
    viewer.show()
    viewer.load_subtitles(cues, list(cues))
    qapp.processEvents()

    # len() reports every cue without building a card for each one...
    assert len(viewer.cards) == 600
    assert viewer.cue_count == 600
    assert viewer.materialized_count < 100

    # ...while indexing still hands back the real, editable card.
    first = viewer.cards[0]
    assert first.edited_item.text == "Cue 0"
    assert viewer.materialized_count < 100

    # Edits live in the cue model, so releasing the widget keeps them.
    first.edit_text.setPlainText("Edited cue")
    assert viewer.get_processed_subtitles()[0].text == "Edited cue"

    viewer.scroll_area.verticalScrollBar().setValue(300 * 60)
    qapp.processEvents()
    assert viewer.card_at(300).edited_item.text == "Cue 300"
    rebuilt = viewer.card_at(0)
    assert rebuilt.edit_text.toPlainText() == "Edited cue"

    # Filtering stays data driven and reports the same counts as before.
    visible, total = viewer.filter_subtitles("Cue 30")
    assert (visible, total) == (11, 600)
    assert viewer.cards[0].isHidden()
    assert not viewer.cards[30].isHidden()
    viewer.filter_subtitles("")
    visible, total = viewer.filter_subtitles("")
    assert (visible, total) == (600, 600)
