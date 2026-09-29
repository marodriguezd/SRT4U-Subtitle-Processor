"""Preview-player state tests that do not depend on multimedia codecs."""

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QMediaPlayer

from application.services.i18n_service import t
from application.ui.widgets import VideoPreviewPlayer


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


def test_player_mute_icon_and_volume_restore_follow_audio_state(qapp):
    player = VideoPreviewPlayer()
    player.player.setSource(QUrl("file:///tmp/fake.mp4"))
    player._media_error = False
    player._refresh_media_controls()

    player.vol_slider.setValue(35)
    assert player.audio_output.volume() == 0.35
    assert player.btn_mute.toolTip() == t("preview.mute_tooltip")

    player._toggle_mute()
    assert player.audio_output.isMuted()
    assert player.btn_mute.toolTip() == t("preview.unmute_tooltip")

    player.vol_slider.setValue(60)
    assert not player.audio_output.isMuted()
    assert player.audio_output.volume() == 0.60
    assert player.btn_mute.toolTip() == t("preview.mute_tooltip")
