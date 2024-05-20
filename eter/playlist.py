"""Resolve .pls / .m3u playlist URLs to a direct stream URL.

The Qt/FFmpeg backend does not reliably follow playlist container files, so we
fetch and parse them ourselves before handing a URL to QMediaPlayer.
"""
from __future__ import annotations

import urllib.request
from urllib.parse import urlparse, urlsplit, urlunsplit

PLAYLIST_EXTS = (".pls", ".m3u", ".m3u8")


def looks_like_playlist(url: str) -> bool:
    return urlparse(url).path.lower().endswith(PLAYLIST_EXTS)


def normalize_stream_url(url: str) -> str:
    """Neutralise SHOUTcast's ``/;stream.nsv`` trick before playback.

    SHOUTcast servers accept a ``/;<anything>`` path but stream identical audio
    from the root. When that suffix carries a ``.nsv`` extension it makes
    FFmpeg's format probe pick the (wrong) NSV demuxer, so playback hangs in
    "buffering" forever. We rewrite only that specific case to the clean root;
    real Icecast mounts (``/live64``, ``/proxy/…``) and other suffixes such as
    ``/;*.mp3`` or a bare ``/;`` are left untouched.
    """
    parts = urlsplit(url)
    head, sep, tail = parts.path.partition(";")
    if sep and head in ("", "/") and tail.lower().endswith(".nsv"):
        return urlunsplit((parts.scheme, parts.netloc, "/", parts.query, parts.fragment))
    return url


def _parse_pls(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("file") and "=" in line:
            candidate = line.split("=", 1)[1].strip()
            if candidate:
                return candidate
    return None


def _parse_m3u(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line
    return None


def resolve_playlist(url: str, timeout: float = 8.0) -> str:
    """Return the first stream URL from a playlist. Blocking network call.

    If ``url`` is not a playlist (or parsing fails), the original URL is
    returned unchanged so playback can still be attempted.
    """
    if not looks_like_playlist(url):
        return url
    req = urllib.request.Request(url, headers={"User-Agent": "eter/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read(65536)
    text = raw.decode("utf-8", errors="replace")
    is_pls = urlparse(url).path.lower().endswith(".pls")
    stream = _parse_pls(text) if is_pls else _parse_m3u(text)
    return stream or url
