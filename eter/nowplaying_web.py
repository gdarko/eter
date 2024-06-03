"""Optional web-based 'now playing' provider.

Some broadcasters (e.g. Naxi) leave the ICY StreamTitle empty but publish the
current song on their website. A station may carry a ``now_playing`` spec:

    {
      "url": "https://www.naxi.rs/cafe",
      "container_class": "song-info",  # optional: scope the search to this element
      "artist_class": "artist",        # text of first element with this CSS class
      "song_class": "song",
      "interval": 15,                   # poll seconds (default 15)
      "format": "{artist} - {song}"     # optional
    }

Alternatively a ``regex`` with named groups (``title`` or ``artist``/``song``)
can extract from any text/JSON endpoint. Everything here is best-effort.
"""
from __future__ import annotations

import html as _html
import re
import threading
import urllib.request
from html.parser import HTMLParser

from PySide6.QtCore import QObject, Signal

_UA = "eter/0.1 (+https://github.com/)"
_VOID = {
    "br", "img", "hr", "input", "meta", "link", "source", "wbr", "area",
    "base", "col", "embed", "param", "track", "use", "path",
}


class _ScopedFields(HTMLParser):
    """Extract text of the first element of each field class, optionally scoped
    to the first element carrying ``container`` class.
    """

    def __init__(self, container: str | None, fields: dict[str, str]):
        super().__init__()
        self._container = container
        self._fields = fields
        self.values: dict[str, str] = {}
        self._in = container is None
        self._depth = 0
        self._field: str | None = None
        self._field_tag: str | None = None
        self._parts: list[str] = []

    def _done(self) -> bool:
        return all(name in self.values for name in self._fields)

    def handle_starttag(self, tag, attrs):
        if self._done():
            return
        classes = (dict(attrs).get("class") or "").split()
        if not self._in:
            if self._container in classes:
                self._in = True
                self._depth = 0 if tag in _VOID else 1
            return
        if tag not in _VOID:
            self._depth += 1
        if self._field is None:
            for name, cls in self._fields.items():
                if name not in self.values and cls in classes:
                    self._field, self._field_tag, self._parts = name, tag, []
                    break

    def handle_endtag(self, tag):
        if self._field is not None and tag == self._field_tag:
            self.values[self._field] = "".join(self._parts).strip()
            self._field = self._field_tag = None
        if self._in and self._container is not None and tag not in _VOID:
            self._depth -= 1
            if self._depth <= 0:
                self._in = False  # left the container; stop scoping

    def handle_data(self, data):
        if self._field is not None:
            self._parts.append(data)


def _extract_fields(markup: str, container: str | None, fields: dict[str, str]) -> dict[str, str]:
    parser = _ScopedFields(container, fields)
    try:
        parser.feed(markup)
    except Exception:  # noqa: BLE001
        pass
    return {k: _html.unescape(v).strip() for k, v in parser.values.items() if v}


def extract_by_class(markup: str, classname: str) -> str | None:
    return _extract_fields(markup, None, {"v": classname}).get("v") or None


def _combine(spec: dict, artist: str | None, song: str | None) -> str | None:
    artist = (artist or "").strip()
    song = (song or "").strip()
    if artist and song:
        return spec.get("format", "{artist} - {song}").format(artist=artist, song=song)
    return song or artist or None


def fetch_now_playing(spec: dict, timeout: float = 8.0) -> str | None:
    """Fetch and parse the current song. Blocking network call, best-effort."""
    url = spec.get("url")
    if not url:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        body = resp.read(300_000).decode("utf-8", errors="replace")

    if spec.get("regex"):
        m = re.search(spec["regex"], body)
        if not m:
            return None
        groups = m.groupdict()
        if groups.get("title"):
            return _html.unescape(groups["title"]).strip() or None
        return _combine(spec, groups.get("artist"), groups.get("song"))

    fields = {}
    if spec.get("artist_class"):
        fields["artist"] = spec["artist_class"]
    if spec.get("song_class"):
        fields["song"] = spec["song_class"]
    found = _extract_fields(body, spec.get("container_class"), fields)
    return _combine(spec, found.get("artist"), found.get("song"))


class WebNowPlayingReader(QObject):
    """Polls a now_playing web spec on a background thread."""

    titleChanged = Signal(str)

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self._spec = spec
        self._interval = max(5.0, float(spec.get("interval", 15)))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: str | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                title = fetch_now_playing(self._spec)
            except Exception:  # noqa: BLE001
                title = None
            if title and title != self._last:
                self._last = title
                self.titleChanged.emit(title)
            self._stop.wait(self._interval)
