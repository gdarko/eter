"""Prepare a station URL for playback (Chain of Responsibility).

Each handler transforms the URL and passes it along: resolve a .pls/.m3u
playlist to its stream, then normalise SHOUTcast's ;stream.nsv trick. The
concrete work reuses eter.playlist.
"""
from __future__ import annotations

from . import playlist


class UrlHandler:
    def __init__(self) -> None:
        self._next: UrlHandler | None = None

    def set_next(self, handler: "UrlHandler") -> "UrlHandler":
        self._next = handler
        return handler

    def handle(self, url: str) -> str:
        url = self._process(url)
        return self._next.handle(url) if self._next else url

    def _process(self, url: str) -> str:
        return url


class PlaylistResolveHandler(UrlHandler):
    def _process(self, url: str) -> str:
        if playlist.looks_like_playlist(url):
            return playlist.resolve_playlist(url)
        return url


class ShoutcastNormalizeHandler(UrlHandler):
    def _process(self, url: str) -> str:
        return playlist.normalize_stream_url(url)


def default_chain() -> UrlHandler:
    head = PlaylistResolveHandler()
    head.set_next(ShoutcastNormalizeHandler())
    return head


def needs_network(url: str) -> bool:
    """True when preparing this URL will do a blocking fetch (playlist)."""
    return playlist.looks_like_playlist(url)


def prepare(url: str) -> str:
    return default_chain().handle(url)
