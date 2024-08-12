from PySide6.QtMultimedia import QMediaPlayer

from eter.player import (
    RECONNECT_BASE_MS,
    RECONNECT_MAX_MS,
    RadioPlayer,
    reconnect_delay,
)


def test_backoff_exponential_and_capped():
    assert reconnect_delay(0) == RECONNECT_BASE_MS
    assert reconnect_delay(1) == 2 * RECONNECT_BASE_MS
    assert reconnect_delay(2) == 4 * RECONNECT_BASE_MS
    assert reconnect_delay(100) == RECONNECT_MAX_MS
    assert reconnect_delay(-5) == RECONNECT_BASE_MS


def test_reconnect_scheduled_on_stream_end():
    p = RadioPlayer()
    states = []
    p.stateChanged.connect(states.append)
    p._intended_url = "http://example/;"  # pretend a station is playing
    p._on_media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    assert "reconnecting" in states
    assert p._reconnect_timer.isActive()
    p._reconnect_timer.stop()  # don't actually fire during the test


def test_no_reconnect_after_user_stop():
    p = RadioPlayer()
    p._intended_url = ""  # user stopped
    states = []
    p.stateChanged.connect(states.append)
    p._on_playback_state(QMediaPlayer.PlaybackState.StoppedState)
    assert "reconnecting" not in states
    assert not p._reconnect_timer.isActive()
