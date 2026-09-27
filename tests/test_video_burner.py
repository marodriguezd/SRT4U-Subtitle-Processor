import os
import subprocess

import pytest

from application.services.i18n_service import get_i18n
from application.services.subtitle_service import SubtitleItem
from application.services.video_burner_service import VideoBurnerService, BurnInOptions
from application.ui.burn_in_dialog import BurnInDialog

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="module")
def sample_clip(tmp_path_factory):
    """Genera un clip de vídeo temporal con FFmpeg para probar la extracción de duración."""
    ffmpeg = VideoBurnerService.get_ffmpeg_path()
    if not ffmpeg:
        pytest.skip("FFmpeg no está disponible en este entorno")

    clip = tmp_path_factory.mktemp("clips") / "clip.mp4"
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x240:d=2",
        "-pix_fmt",
        "yuv420p",
        str(clip),
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )
    if result.returncode != 0 or not clip.exists():
        pytest.skip("No se pudo generar el clip de prueba con FFmpeg")
    return str(clip)


def test_ffmpeg_detection():
    path = VideoBurnerService.get_ffmpeg_path()
    assert path is not None
    assert os.path.exists(path)


def test_generate_ass_script_styles():
    items = [
        SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="First line"),
        SubtitleItem(
            index=2, start_ms=4000, end_ms=7000, text="Second line with\nbreak"
        ),
    ]

    # Test Default (medium, white, semi)
    opts_default = BurnInOptions()
    script = VideoBurnerService.generate_ass_script(items, opts_default)
    assert "[Script Info]" in script
    assert "PlayResX: 1920" in script
    assert "PlayResY: 1080" in script
    assert "Style: Default,sans-serif,49,&H00FFFFFF" in script
    assert "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,First line" in script
    assert "Second line with\\Nbreak" in script

    # Test large, yellow, solid
    opts_yellow = BurnInOptions(
        font_size="large",
        font_color="yellow",
        box_style="solid",
    )
    script_yellow = VideoBurnerService.generate_ass_script(items, opts_yellow)
    assert "Style: Default,sans-serif,63,&H0000FFFF" in script_yellow

    # Test small, cyan, none
    opts_cyan = BurnInOptions(
        font_size="small",
        font_color="cyan",
        box_style="none",
    )
    script_cyan = VideoBurnerService.generate_ass_script(items, opts_cyan)
    assert "Style: Default,sans-serif,38,&H00FFFF00" in script_cyan


def test_overlap_sanitization():
    items = [
        SubtitleItem(index=1, start_ms=1000, end_ms=5000, text="Overlap 1"),
        SubtitleItem(index=2, start_ms=4000, end_ms=7000, text="Overlap 2"),
    ]
    script_fixed = VideoBurnerService.generate_ass_script(
        items, BurnInOptions(fix_overlaps=True)
    )
    assert "Dialogue: 0,0:00:01.00,0:00:03.96,Default,,0,0,0,,Overlap 1" in script_fixed
    assert "Dialogue: 0,0:00:04.00,0:00:07.00,Default,,0,0,0,,Overlap 2" in script_fixed


def test_video_duration_extraction(sample_clip):
    duration = VideoBurnerService.get_video_duration_ms(sample_clip)
    assert duration is not None
    # El clip generado dura 2 segundos
    assert 1500 <= duration <= 3000


def test_burn_in_dialog_ui(qapp):
    get_i18n().set_language("es", save_to_config=False)
    items = [
        SubtitleItem(index=1, start_ms=1000, end_ms=3000, text="Hola mundo"),
    ]
    dlg = BurnInDialog(video_path="/path/test.mp4", subtitle_items=items)
    assert dlg.txt_video.text() == "/path/test.mp4"
    assert dlg.txt_output.text() == "/path/test_subtitulado.mp4"
    assert "1 líneas" in dlg.lbl_sub_badge.text()

    # Cambiar opciones y verificar que los valores internos se mantienen estables
    dlg.cb_color.setCurrentIndex(dlg.cb_color.findData("yellow"))
    dlg.cb_size.setCurrentIndex(dlg.cb_size.findData("large"))
    dlg.cb_box.setCurrentIndex(dlg.cb_box.findData("solid"))
    assert dlg.cb_color.currentData() == "yellow"
    assert dlg.cb_size.currentData() == "large"
    assert dlg.cb_box.currentData() == "solid"
    assert dlg.chk_fix_overlaps.isChecked() is True
