"""Persistence for the catalog (Repository).

Isolates JSON load/save (with atomic writes) from the domain model, and seeds a
fresh catalog from the bundled default packs on first run.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .catalog import Catalog
from .seeder import DefaultCatalogSeeder


class CatalogRepository:
    def __init__(self, path: Path | None = None):
        self._path = path or config.catalog_file()

    def load(self) -> Catalog:
        obj = self._read()
        if obj and obj.get("version") == Catalog.VERSION and obj.get("packs"):
            return Catalog.from_dict(obj)
        # Missing or older format: seed fresh (the app is pre-launch, no migration).
        catalog = DefaultCatalogSeeder().build()
        self.save(catalog)
        return catalog

    def save(self, catalog: Catalog) -> None:
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(
            json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)  # atomic on POSIX/Windows

    def _read(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
