# tests/test_video_burner.py
import os
import sys
import pytest
from PyQt6.QtWidgets import QApplication

from application.services.subtitle_service import SubtitleItem
from application.services.video_burner_service import VideoBurnerService, BurnInOptions
from application.ui.burn_in_dialog import BurnInDialog, BurnInProgressModal

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_CLIP = "/home/marodriguezd/Descargas/clips_output/clip_1_00-00_to_02-00.mp4"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_ffmpeg_detection():
    path = VideoBurnerService.get_ffmpeg_path()
    assert path is not None
    assert os.path.exists(path)


def test_generate_ass_script_styles():
    items = [
        SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="First line"),
        SubtitleItem(index=2, start_ms=4000, end_ms=7000, text="Second line with\nbreak"),
    ]

    # Test Default (Mediano, Blanco, Caja semitransparente)
    opts_default = BurnInOptions()
    script = VideoBurnerService.generate_ass_script(items, opts_default)
    assert "[Script Info]" in script
    assert "PlayResX: 1920" in script
    assert "PlayResY: 1080" in script
    assert "Style: Default,sans-serif,49,&H00FFFFFF" in script
    assert "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,First line" in script
    assert "Second line with\\Nbreak" in script

    # Test Grande, Amarillo, Caja sólida
    opts_yellow = BurnInOptions(
        font_size="Grande",
        font_color="Amarillo",
        box_style="Caja sólida",
    )
    script_yellow = VideoBurnerService.generate_ass_script(items, opts_yellow)
    assert "Style: Default,sans-serif,63,&H0000FFFF" in script_yellow

    # Test Pequeño, Cian, Sin fondo
    opts_cyan = BurnInOptions(
        font_size="Pequeño",
        font_color="Cian",
        box_style="Sin fondo",
    )
    script_cyan = VideoBurnerService.generate_ass_script(items, opts_cyan)
    assert "Style: Default,sans-serif,38,&H00FFFF00" in script_cyan


def test_overlap_sanitization():
    items = [
        SubtitleItem(index=1, start_ms=1000, end_ms=5000, text="Overlap 1"),
        SubtitleItem(index=2, start_ms=4000, end_ms=7000, text="Overlap 2"),
    ]
    script_fixed = VideoBurnerService.generate_ass_script(items, BurnInOptions(fix_overlaps=True))
    assert "Dialogue: 0,0:00:01.00,0:00:03.96,Default,,0,0,0,,Overlap 1" in script_fixed
    assert "Dialogue: 0,0:00:04.00,0:00:07.00,Default,,0,0,0,,Overlap 2" in script_fixed


def test_video_duration_extraction():
    if os.path.exists(SAMPLE_CLIP):
        duration = VideoBurnerService.get_video_duration_ms(SAMPLE_CLIP)
        assert duration is not None
        # Clip es de ~2 minutos (120000 ms)
        assert 110000 <= duration <= 130000


def test_burn_in_dialog_ui(qapp):
    items = [
        SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="Hola mundo"),
    ]
    dlg = BurnInDialog(video_path="/path/test.mp4", subtitle_items=items)
    assert dlg.txt_video.text() == "/path/test.mp4"
    assert dlg.txt_output.text() == "/path/test_subtitulado.mp4"
    assert "1 líneas" in dlg.lbl_sub_badge.text()

    # Cambiar opciones y verificar preview
    dlg.cb_color.setCurrentText("Amarillo")
    dlg.cb_size.setCurrentText("Grande")
    dlg.cb_box.setCurrentText("Caja sólida")
    assert dlg.cb_color.currentText() == "Amarillo"
    assert dlg.chk_fix_overlaps.isChecked() is True
