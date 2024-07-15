"""Lightweight GitHub-release update checker (notify only, no auto-install).

Queries the GitHub Releases API for the latest tag and compares it to the
running version. Set the repo via the ETER_GITHUB_REPO env var or edit
GITHUB_REPO below. Missing repo / offline / no releases → silently no-op.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

GITHUB_REPO = os.environ.get("ETER_GITHUB_REPO", "gdarko/eter")


def parse_version(s: str) -> tuple[int, int, int]:
    """Parse 'v1.2.3' / '1.2' into a 3-tuple, ignoring any suffix."""
    s = (s or "").strip().lstrip("vV")
    parts: list[int] = []
    for token in s.split(".")[:3]:
        digits = ""
        for ch in token:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)  # type: ignore[return-value]


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def fetch_latest_release(repo: str = GITHUB_REPO, timeout: float = 8.0) -> dict | None:
    """Return {'version','url','name'} for the latest release, or None."""
    if not repo:
        return None
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "eter-updater",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read(200_000).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - offline / 404 / rate-limited
        return None
    tag = data.get("tag_name") or data.get("name") or ""
    if not tag:
        return None
    return {"version": tag, "url": data.get("html_url", ""), "name": data.get("name") or tag}


class UpdateChecker(QObject):
    """Checks for updates on a background thread and reports via signals."""

    updateAvailable = Signal(str, str)  # version, html_url
    noUpdate = Signal()
    failed = Signal(str)

    def __init__(self, current_version: str, repo: str = GITHUB_REPO, parent=None):
        super().__init__(parent)
        self._current = current_version
        self._repo = repo

    def check(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        release = fetch_latest_release(self._repo)
        if not release:
            self.failed.emit("Could not check for updates.")
            return
        if is_newer(release["version"], self._current):
            self.updateAvailable.emit(release["version"], release["url"])
        else:
            self.noUpdate.emit()
