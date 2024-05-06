"""Application constants, config paths, and preference storage."""
from __future__ import annotations

import json
import os
from importlib import resources
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

APP_NAME = "eter"
ORG_NAME = "eter"
ORG_DOMAIN = "eter.app"
DISPLAY_NAME = "eter"

# Curated packs are also served raw from GitHub so they can be updated between
# app releases. Override with ETER_PACKS_URL (e.g. a local dir during testing).
REMOTE_PACKS_URL = os.environ.get(
    "ETER_PACKS_URL",
    "https://raw.githubusercontent.com/gdarko/eter/main/eter/resources/presets/",
)


def config_dir() -> Path:
    """Per-user writable config directory (created if missing)."""
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )
    if not base:
        base = str(Path.home() / ".config" / APP_NAME)
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def catalog_file() -> Path:
    """Path to the user-editable, pack-centric catalog."""
    return config_dir() / "catalog.json"


# ---- starter packs (bundled presets, mirrored by the remote manifest) ----
def _preset(name: str):
    return resources.files("eter.resources").joinpath("presets", name)


def _preset_obj(name: str) -> dict:
    try:
        return json.loads(_preset(name).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def bundled_manifest() -> list[dict]:
    """[{id, name, version}] for the bundled packs, from index.json."""
    return _preset_obj("index.json").get("packs", [])


def available_packs() -> list[tuple[str, str]]:
    """(pack_id, display_name) for each bundled pack, in display order."""
    return [(p["id"], p.get("name", p["id"])) for p in bundled_manifest()]


def _pack_obj(pack_id: str) -> dict:
    return _preset_obj(f"{pack_id}.json")


def pack_version(pack_id: str) -> int:
    return int(_pack_obj(pack_id).get("version", 1))


def load_pack(pack_id: str) -> list[dict]:
    """Station dicts for one bundled pack."""
    return _pack_obj(pack_id).get("stations", [])


def all_pack_stations() -> list[dict]:
    """Every station across all bundled packs (used for now_playing backfill)."""
    out: list[dict] = []
    for p in bundled_manifest():
        out.extend(load_pack(p["id"]))
    return out


def settings() -> QSettings:
    """Native per-OS key/value store for user preferences."""
    return QSettings(ORG_NAME, APP_NAME)


def known_source_ids() -> set[str]:
    """Curated pack ids the app has ever seeded / installed / dismissed."""
    v = settings().value("known_source_ids", [])
    if isinstance(v, str):
        return {v} if v else set()
    return {str(x) for x in (v or [])}


def add_known_source_ids(ids) -> None:
    settings().setValue("known_source_ids", sorted(known_source_ids() | set(ids)))
