"""'Now playing' sources (Strategy).

Each MetadataSource resolves the current song a different way and emits
titleChanged. Authoritative sources (Qt metadata, ICY StreamTitle) outrank the
web fallback; the NowPlayingResolver composes them.
"""
from __future__ import annotations

import socket
import ssl
import threading
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtMultimedia import QMediaMetaData, QMediaPlayer

from .nowplaying_web import WebNowPlayingReader


def parse_stream_title(meta: bytes) -> str | None:
    """Extract StreamTitle='...' from an ICY metadata block."""
    text = meta.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    marker = "StreamTitle='"
    start = text.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = text.find("';", start)
    if end < 0:
        end = text.find("'", start)
    if end < 0:
        return None
    return text[start:end].strip()


class _IcyReader(QObject):
    """Reads ICY StreamTitle over a raw socket (handles SHOUTcast 'ICY 200 OK')."""

    titleChanged = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._last = ""

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def _run(self) -> None:
        try:
            self._read_loop()
        except Exception:  # noqa: BLE001 - metadata is best-effort
            pass

    def _read_loop(self) -> None:
        u = urlsplit(self._url)  # keeps ";stream.nsv" in the path
        host = u.hostname
        if not host:
            return
        port = u.port or (443 if u.scheme == "https" else 80)
        path = (u.path or "/") + (("?" + u.query) if u.query else "")

        sock = socket.create_connection((host, port), timeout=15)
        if u.scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        self._sock = sock
        sock.sendall(
            (
                f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: eter/0.1\r\n"
                f"Icy-MetaData: 1\r\nAccept: */*\r\nConnection: close\r\n\r\n"
            ).encode("latin-1")
        )

        buf = b""
        while b"\r\n\r\n" not in buf:
            if self._stop.is_set():
                return
            chunk = sock.recv(1024)
            if not chunk:
                return
            buf += chunk
            if len(buf) > 65536:
                return
        header_blob, _, rest = buf.partition(b"\r\n\r\n")
        metaint = None
        for line in header_blob.split(b"\r\n")[1:]:
            if line.lower().startswith(b"icy-metaint:"):
                val = line.split(b":", 1)[1].strip()
                if val.isdigit():
                    metaint = int(val)
        if not metaint:
            return
        self._consume(sock, rest, metaint)

    def _consume(self, sock, prebuf: bytes, metaint: int) -> None:
        buf = prebuf
        while not self._stop.is_set():
            buf = self._read_at_least(sock, buf, metaint)
            if buf is None:
                return
            audio, buf = buf[:metaint], buf[metaint:]  # noqa: F841 - discard audio
            buf = self._read_at_least(sock, buf, 1)
            if buf is None:
                return
            length = buf[0] * 16
            buf = buf[1:]
            if length:
                buf = self._read_at_least(sock, buf, length)
                if buf is None:
                    return
                meta, buf = buf[:length], buf[length:]
                title = parse_stream_title(meta)
                if title is not None and title != self._last:
                    self._last = title
                    self.titleChanged.emit(title)

    def _read_at_least(self, sock, buf: bytes, n: int):
        while len(buf) < n:
            if self._stop.is_set():
                return None
            chunk = sock.recv(max(1, n - len(buf)))
            if not chunk:
                return None
            buf += chunk
        return buf


class MetadataSource(QObject):
    """Base source: start/stop resolving the current title for a station."""

    titleChanged = Signal(str)
    AUTHORITATIVE = False  # real StreamTitle outranks the web fallback

    def start(self, station) -> None:  # noqa: D401
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class QtMetadataSource(MetadataSource):
    AUTHORITATIVE = True

    def __init__(self, media_player: QMediaPlayer, parent=None):
        super().__init__(parent)
        self._player = media_player
        self._active = False
        self._player.metaDataChanged.connect(self._on_meta)

    def start(self, station) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False

    @Slot()
    def _on_meta(self) -> None:
        if not self._active:
            return
        md = self._player.metaData()
        title = md.value(QMediaMetaData.Key.Title) or md.value(QMediaMetaData.Key.Comment)
        if title:
            self.titleChanged.emit(str(title))


class IcyStreamSource(MetadataSource):
    AUTHORITATIVE = True
    GRACE_MS = 5000  # give Qt metadata a chance before opening a second socket

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reader: _IcyReader | None = None
        self._url = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._begin)

    def start(self, station) -> None:
        self.stop()
        self._url = station.url
        self._timer.start(self.GRACE_MS)

    def stop(self) -> None:
        self._timer.stop()
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        self._url = ""

    @Slot()
    def _begin(self) -> None:
        if not self._url:
            return
        self._reader = _IcyReader(self._url, self)
        self._reader.titleChanged.connect(self.titleChanged)
        self._reader.start()


class WebScrapeSource(MetadataSource):
    AUTHORITATIVE = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reader: WebNowPlayingReader | None = None

    def start(self, station) -> None:
        self.stop()
        spec = getattr(station, "now_playing", None)
        if spec:
            self._reader = WebNowPlayingReader(spec, self)
            self._reader.titleChanged.connect(self.titleChanged)
            self._reader.start()

    def stop(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
