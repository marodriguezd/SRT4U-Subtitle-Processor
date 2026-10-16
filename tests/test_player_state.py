"""Preview-player state tests that do not depend on multimedia codecs."""

import pytest
from PyQt6.QtCore import QUrl

from application.services.i18n_service import t
from application.ui.widgets import MULTIMEDIA_AVAILABLE, VideoPreviewPlayer

if not MULTIMEDIA_AVAILABLE:
    QMediaPlayer = None  # type: ignore[assignment,misc]
else:
    from PyQt6.QtMultimedia import QMediaPlayer


@pytest.mark.skipif(
    not MULTIMEDIA_AVAILABLE,
    reason="PyQt6.QtMultimedia requires system audio library (e.g. libpulse)",
)
def test_player_controls_follow_source_and_duration(qapp):
    player = VideoPreviewPlayer()
    assert not player.play_btn.isEnabled()
    assert not player.time_slider.isEnabled()
    assert not player.btn_mute.isEnabled()
    assert not player.vol_slider.isEnabled()

    player.player.setSource(QUrl("file:///tmp/fake.mp4"))
    player._media_error = False
    player._refresh_media_controls()
    assert player.play_btn.isEnabled()
    assert not player.time_slider.isEnabled()
    assert player.btn_mute.isEnabled()
    assert player.vol_slider.isEnabled()

    player._on_duration_changed(1000)
    assert player.time_slider.isEnabled()

    player._on_media_error(QMediaPlayer.Error.FormatError, "private backend details")
    assert not player.play_btn.isEnabled()
    assert not player.time_slider.isEnabled()
    assert not player.btn_mute.isEnabled()
    assert not player.vol_slider.isEnabled()
    assert "private backend details" not in player.sub_overlay.text()


@pytest.mark.skipif(
    not MULTIMEDIA_AVAILABLE,
    reason="PyQt6.QtMultimedia requires system audio library (e.g. libpulse)",
)
def test_player_mute_icon_and_volume_restore_follow_audio_state(qapp):
    player = VideoPreviewPlayer()
    player.player.setSource(QUrl("file:///tmp/fake.mp4"))
    player._media_error = False
    player._refresh_media_controls()

    player.vol_slider.setValue(35)
    assert player.audio_output.volume() == pytest.approx(0.35, abs=1e-6)
    assert player.btn_mute.toolTip() == t("preview.mute_tooltip")

    player._toggle_mute()
    assert player.audio_output.isMuted()
    assert player.btn_mute.toolTip() == t("preview.unmute_tooltip")

    player.vol_slider.setValue(60)
    assert not player.audio_output.isMuted()
    assert player.audio_output.volume() == pytest.approx(0.60, abs=1e-6)
    assert player.btn_mute.toolTip() == t("preview.mute_tooltip")


def test_player_degrades_gracefully_when_multimedia_unavailable(qapp, monkeypatch):
    """When QtMultimedia is absent, VideoPreviewPlayer initializes cleanly and stays disabled."""
    import application.ui.widgets as widgets

    monkeypatch.setattr(widgets, "MULTIMEDIA_AVAILABLE", False)
    player = widgets.VideoPreviewPlayer()
    assert player.player is None
    assert player.audio_output is None
    assert player.video_widget is None
    assert not player.play_btn.isEnabled()
    assert not player.time_slider.isEnabled()
    assert not player.btn_mute.isEnabled()
    assert not player.vol_slider.isEnabled()

    # Public operations must be safe no-ops without throwing AttributeError
    player.load_video("/tmp/nonexistent.mp4")
    player.seek_to_ms(500)
    player._toggle_playback()
    player._set_position(100)
    player.retranslate()
    player.set_subtitles([])
    player._refresh_media_controls()
    assert not player.play_btn.isEnabled()
