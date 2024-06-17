"""Seed a fresh catalog from the bundled default packs (Factory Method)."""
from __future__ import annotations

from . import config
from .catalog import Catalog, Pack, Station


class DefaultCatalogSeeder:
    """Builds the initial Catalog: curated packs (managed) + an empty user pack,
    lifting any `favorite: true` in the presets into the favourites overlay."""

    def build(self) -> Catalog:
        packs: list[Pack] = []
        favorites: set[str] = set()
        for pack_id, name in config.available_packs():
            stations: list[Station] = []
            for d in config.load_pack(pack_id):
                if not d.get("url"):
                    continue
                st = Station.from_dict(d)
                stations.append(st)
                if d.get("favorite"):
                    favorites.add(st.url)
            packs.append(
                Pack(
                    id=pack_id,
                    name=name,
                    visible=True,
                    stations=stations,
                    source_id=pack_id,
                    source_version=config.pack_version(pack_id),
                )
            )
        packs.append(Pack(id="custom", name="My Stations", visible=True, stations=[]))
        config.add_known_source_ids(p.source_id for p in packs if p.source_id)
        return Catalog(packs, favorites)
