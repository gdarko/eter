"""Audio playback.

RadioPlayer is a Facade over the Qt Multimedia subsystem (QMediaPlayer,
QAudioOutput) plus URL preparation and auto-reconnect, exposing one small
domain API (play / stop / set_volume + signals).
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from . import urlprep

# Auto-reconnect backoff for dropped streams.
RECONNECT_BASE_MS = 1000
RECONNECT_MAX_MS = 15000


def reconnect_delay(attempts: int, base: int = RECONNECT_BASE_MS, cap: int = RECONNECT_MAX_MS) -> int:
    """Exponential backoff in ms, capped. attempts=0 -> base."""
    return min(cap, base * (2 ** max(0, attempts)))


class RadioPlayer(QObject):
    """Thin wrapper around QMediaPlayer + QAudioOutput for internet radio.

    ``state`` strings emitted: connecting, buffering, playing, stopped, error.
    """

    stateChanged = Signal(str)
    errorText = Signal(str)

    # internal, used to hop playlist resolution back onto the GUI thread
    _resolved = Signal(str)
    _resolveFailed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio)
        self._current_url = ""

        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)
        self._resolved.connect(self._start_source)
        self._resolveFailed.connect(self._on_resolve_failed)

        # auto-reconnect state
        self._intended_url = ""       # the stream we want playing ("" = user stopped)
        self._reconnect_attempts = 0
        self._manual_reload = False   # ignore transient Stopped during our own reload
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._do_reconnect)

    @property
    def media_player(self) -> QMediaPlayer:
        return self._player

    # ---- controls ----
    def set_volume(self, value: float) -> None:
        self._audio.setVolume(max(0.0, min(1.0, value)))

    def volume(self) -> float:
        return float(self._audio.volume())

    def play(self, url: str) -> None:
        self._reconnect_attempts = 0
        self._reconnect_timer.stop()
        self.stateChanged.emit("connecting")
        if urlprep.needs_network(url):  # playlist fetch off the GUI thread
            threading.Thread(
                target=self._prepare_worker, args=(url,), daemon=True
            ).start()
        else:
            self._start_source(urlprep.prepare(url))

    def stop(self) -> None:
        self._intended_url = ""
        self._reconnect_timer.stop()
        self._reconnect_attempts = 0
        self._player.stop()
        self._player.setSource(QUrl())
        self.stateChanged.emit("stopped")

    def is_active(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    # ---- internals ----
    def _prepare_worker(self, url: str) -> None:
        try:
            self._resolved.emit(urlprep.prepare(url))
        except Exception as exc:  # noqa: BLE001 - report any resolution failure
            self._resolveFailed.emit(str(exc))

    @Slot(str)
    def _start_source(self, url: str) -> None:
        self._current_url = url
        self._intended_url = url
        self._manual_reload = True
        self._player.setSource(QUrl(url))
        self._player.play()

    @Slot(str)
    def _on_resolve_failed(self, msg: str) -> None:
        self.errorText.emit(f"Could not resolve playlist: {msg}")
        self.stateChanged.emit("error")

    def _on_playback_state(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._manual_reload = False
            self._reconnect_attempts = 0
            self.stateChanged.emit("playing")
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            if self._manual_reload:
                return  # our own setSource() churn, not a real stop
            if self._intended_url:
                self._schedule_reconnect()  # unexpected drop
            else:
                self.stateChanged.emit("stopped")

    def _on_media_status(self, status) -> None:
        S = QMediaPlayer.MediaStatus
        if status in (S.LoadingMedia, S.BufferingMedia, S.StalledMedia):
            self._manual_reload = False
            self.stateChanged.emit("buffering")
        elif status == S.BufferedMedia:
            self._manual_reload = False
            self._reconnect_attempts = 0
            self.stateChanged.emit("playing")
        elif status in (S.EndOfMedia, S.InvalidMedia) and self._intended_url:
            self._schedule_reconnect()  # live stream ended = dropped

    def _on_error(self, error, error_string: str = "") -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        if self._intended_url:
            if self._reconnect_attempts == 0:
                self.errorText.emit(error_string or "Stream error — reconnecting…")
            self._schedule_reconnect()
        else:
            self.errorText.emit(error_string or "Playback error")
            self.stateChanged.emit("error")

    def _schedule_reconnect(self) -> None:
        if not self._intended_url or self._reconnect_timer.isActive():
            return
        self.stateChanged.emit("reconnecting")
        self._reconnect_timer.start(reconnect_delay(self._reconnect_attempts))

    def _do_reconnect(self) -> None:
        if not self._intended_url:
            return
        self._reconnect_attempts += 1
        url = self._intended_url
        self._manual_reload = True
        self._player.setSource(QUrl())
        self._player.setSource(QUrl(url))
        self._player.play()
