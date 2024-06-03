"""Resolve the current song from several sources.

Holds MetadataSource strategies and merges them: a real ICY StreamTitle (from Qt
metadata or the socket source) always outranks the optional web fallback.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtMultimedia import QMediaPlayer

from .metadata_sources import (
    IcyStreamSource,
    QtMetadataSource,
    WebScrapeSource,
    parse_stream_title,  # re-exported for tests
)

__all__ = ["NowPlayingResolver", "parse_stream_title"]


class NowPlayingResolver(QObject):
    titleChanged = Signal(str)  # "" clears the current song

    def __init__(self, media_player: QMediaPlayer, parent=None):
        super().__init__(parent)
        self._qt = QtMetadataSource(media_player, self)
        self._icy = IcyStreamSource(self)
        self._web = WebScrapeSource(self)
        self._authoritative = ""
        self._web_title = ""
        self._display = ""
        self._qt.titleChanged.connect(self._on_qt_title)
        self._icy.titleChanged.connect(self._on_authoritative)
        self._web.titleChanged.connect(self._on_web_title)

    def start(self, station) -> None:
        self.stop()
        self._authoritative = ""
        self._web_title = ""
        self._display = ""
        self.titleChanged.emit("")
        for src in (self._qt, self._icy, self._web):
            src.start(station)

    def stop(self) -> None:
        for src in (self._qt, self._icy, self._web):
            src.stop()

    @Slot(str)
    def _on_qt_title(self, title: str) -> None:
        if title:
            self._icy.stop()  # Qt delivered it; skip the extra socket
        self._on_authoritative(title)

    @Slot(str)
    def _on_authoritative(self, title: str) -> None:
        self._authoritative = title or ""
        self._emit()

    @Slot(str)
    def _on_web_title(self, title: str) -> None:
        self._web_title = title or ""
        self._emit()

    def _emit(self) -> None:
        display = self._authoritative or self._web_title or ""
        if display != self._display:
            self._display = display
            self.titleChanged.emit(display)
