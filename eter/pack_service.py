"""Fetch curated packs from GitHub (remote Repository/Gateway).

Reads the manifest and individual pack files served raw from the repo, so packs
can be updated between app releases. Best-effort and offline-safe (failures are
silent, mirroring updater.py).
"""
from __future__ import annotations

import json
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from . import config
from .catalog import Station

_UA = "eter/0.1 (packs)"


def _fetch_json(url: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read(1_000_000).decode("utf-8", "replace"))


class RemotePackService(QObject):
    manifestReady = Signal(list)              # [(id, name, version)]
    packReady = Signal(str, str, int, list)   # id, name, version, [Station]
    failed = Signal(str)

    def __init__(self, base_url: str | None = None, parent=None):
        super().__init__(parent)
        self._base = (base_url or config.REMOTE_PACKS_URL).rstrip("/") + "/"

    def check(self) -> None:
        threading.Thread(target=self._check, daemon=True).start()

    def fetch_pack(self, pack_id: str) -> None:
        threading.Thread(target=self._fetch_pack, args=(pack_id,), daemon=True).start()

    # ---- workers ----
    def _check(self) -> None:
        try:
            obj = _fetch_json(self._base + "index.json")
            out = [
                (str(p["id"]), str(p.get("name", p["id"])), int(p.get("version", 1)))
                for p in obj.get("packs", [])
                if p.get("id")
            ]
        except Exception:  # noqa: BLE001
            self.failed.emit("Could not check for pack updates.")
            return
        self.manifestReady.emit(out)

    def _fetch_pack(self, pack_id: str) -> None:
        try:
            obj = _fetch_json(self._base + f"{pack_id}.json")
            stations = [
                Station.from_dict(s) for s in obj.get("stations", []) if s.get("url")
            ]
        except Exception:  # noqa: BLE001
            self.failed.emit(f"Could not fetch pack '{pack_id}'.")
            return
        self.packReady.emit(
            str(obj.get("id", pack_id)),
            str(obj.get("name", pack_id)),
            int(obj.get("version", 1)),
            stations,
        )
