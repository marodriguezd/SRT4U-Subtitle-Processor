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
    """Generate a temporary video clip with FFmpeg to test duration extraction."""
    ffmpeg = VideoBurnerService.get_ffmpeg_path()
    if not ffmpeg:
        pytest.skip("FFmpeg is not available in this environment")

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
        pytest.skip("Could not generate the test clip with FFmpeg")
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


def _dialogue_texts(script):
    """Text of each ``Dialogue:`` line.

    The ASS format is ``Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,
    Effect,Text``, so the text is field 10. Do not split on ``,,`` because
    the line holds two and the text itself may hold more.
    """
    texts = []
    for line in script.splitlines():
        if line.startswith("Dialogue:"):
            fields = line.split(",", 9)
            assert len(fields) == 10, line
            texts.append(fields[9])
    return texts


def test_ass_user_text_cannot_inject_override_tags():
    """A brace in user text cannot open an override block.

    In ASS ``{`` starts an override block, so without escaping a subtitle with
    ``{\\b1}``Bold`` would change the render. These cases check the
    resulting ASS representation, not just that the function returns a string.
    """
    hostile = [
        "{test}",
        r"{\b1}texto",
        r"{\an8}texto",
        "{}",
        "{malicious:tag}",
        "texto { dentro }",
        "texto } fuera",
        r"{\p1}m 0 0 l 9 9 9 9{\p0}dibujo",
    ]
    items = [
        SubtitleItem(index=idx, start_ms=1000, end_ms=2000, text=text)
        for idx, text in enumerate(hostile, start=1)
    ]
    script = VideoBurnerService.generate_ass_script(items, BurnInOptions())

    # No line may start with an unescaped brace: that would be an override.
    for rendered in _dialogue_texts(script):
        assert not rendered.startswith("{"), rendered
        # Every brace present is escaped, so it opens no override block.
        index = 0
        while index < len(rendered):
            char = rendered[index]
            if char in "{}":
                assert rendered[index - 1] == "\\", rendered
            index += 1

    # And meaning is preserved: an escaped brace is a literal brace.
    texts = _dialogue_texts(script)
    assert texts[0] == r"\{test\}"
    assert texts[1] == r"\{\b1\}texto"
    assert texts[3] == r"\{\}"
    assert texts[5] == r"texto \{ dentro \}"


def test_ass_legitimate_tags_and_escapes_survive():
    """User escaping must not break what SRT4U itself generates."""
    items = [
        SubtitleItem(index=1, start_ms=1000, end_ms=2000, text="<i>A</i> y <b>B</b>"),
        SubtitleItem(index=2, start_ms=3000, end_ms=4000, text="primera\nsegunda"),
    ]
    script = VideoBurnerService.generate_ass_script(items, BurnInOptions())
    texts = _dialogue_texts(script)

    # Real ASS tags generated by the app from HTML markup.
    assert texts[0] == r"{\i1}A{\i0} y {\b1}B{\b0}"
    # A real line break stays a \N.
    assert texts[1] == r"primera\Nsegunda"


def test_video_duration_extraction(sample_clip):
    duration = VideoBurnerService.get_video_duration_ms(sample_clip)
    assert duration is not None
    # The generated clip lasts 2 seconds
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

    # Change options and verify the internal values stay stable
    dlg.cb_color.setCurrentIndex(dlg.cb_color.findData("yellow"))
    dlg.cb_size.setCurrentIndex(dlg.cb_size.findData("large"))
    dlg.cb_box.setCurrentIndex(dlg.cb_box.findData("solid"))
    assert dlg.cb_color.currentData() == "yellow"
    assert dlg.cb_size.currentData() == "large"
    assert dlg.cb_box.currentData() == "solid"
    assert dlg.chk_fix_overlaps.isChecked() is True
