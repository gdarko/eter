"""Domain model for the station catalog.

The catalog is a small tree (Composite): a Catalog holds Packs, a Pack groups
Stations by an optional sub-group, and Station is a leaf. Catalog is the
aggregate root and the change subject (Observer, via a Qt signal).

Curated packs (those with a `source_id`) are read-only mirrors of a remote pack:
they are replaced wholesale on update, and the user customises by cloning one into
an editable pack. Favourites are a catalog-level overlay of station URLs, so a user
can star a curated station without editing it.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal


class CatalogNode:
    """Composite component: a uniform node in the catalog tree."""

    @property
    def label(self) -> str:
        raise NotImplementedError

    def children(self) -> list["CatalogNode"]:
        return []

    def is_leaf(self) -> bool:
        return not self.children()


@dataclass
class Station(CatalogNode):
    name: str
    url: str
    group: str = "General"
    now_playing: dict | None = None

    @property
    def label(self) -> str:
        return self.name

    @classmethod
    def from_dict(cls, d: dict) -> "Station":
        np = d.get("now_playing")
        return cls(
            name=str(d.get("name", "")).strip(),
            url=str(d.get("url", "")).strip(),
            group=(str(d.get("group", "General")).strip() or "General"),
            now_playing=np if isinstance(np, dict) else None,
        )

    def to_dict(self) -> dict:
        d = {"name": self.name, "url": self.url, "group": self.group}
        if self.now_playing:
            d["now_playing"] = self.now_playing
        return d

    def key(self) -> str:
        return f"{self.group}\x00{self.name}\x00{self.url}"


@dataclass
class Group(CatalogNode):
    """Derived composite: a named bucket of stations inside a pack."""

    name: str
    stations: list[Station]

    @property
    def label(self) -> str:
        return self.name

    def children(self) -> list[CatalogNode]:
        return list(self.stations)


@dataclass
class Pack(CatalogNode):
    id: str
    name: str
    visible: bool = True
    stations: list[Station] = field(default_factory=list)
    source_id: str | None = None      # set => curated (read-only mirror of remote)
    source_version: int = 0

    @property
    def label(self) -> str:
        return self.name

    @property
    def is_managed(self) -> bool:
        return self.source_id is not None

    def groups(self) -> list[Group]:
        order: list[str] = []
        buckets: dict[str, list[Station]] = {}
        for s in self.stations:
            if s.group not in buckets:
                buckets[s.group] = []
                order.append(s.group)
            buckets[s.group].append(s)
        return [Group(g, buckets[g]) for g in order]

    def children(self) -> list[CatalogNode]:
        return self.groups()

    @classmethod
    def from_dict(cls, d: dict) -> "Pack":
        return cls(
            id=str(d.get("id", "")).strip() or _slug(d.get("name", "pack")),
            name=str(d.get("name", "Pack")).strip() or "Pack",
            visible=bool(d.get("visible", True)),
            stations=[Station.from_dict(s) for s in d.get("stations", []) if s.get("url")],
            source_id=(d.get("source_id") or None),
            source_version=int(d.get("source_version", 0)),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "visible": self.visible,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "stations": [s.to_dict() for s in self.stations],
        }


class CatalogMemento:
    """Snapshot of the whole catalog used to undo edits (Memento)."""

    def __init__(self, packs: list[dict], favorites: list[str]):
        self._packs = packs
        self._favorites = favorites

    def packs(self) -> list[Pack]:
        return [Pack.from_dict(p) for p in copy.deepcopy(self._packs)]

    def favorites(self) -> set[str]:
        return set(self._favorites)


class Catalog(QObject):
    """Aggregate root + change subject. Mutations emit `changed`."""

    VERSION = 4
    changed = Signal()

    def __init__(self, packs: list[Pack] | None = None, favorites: set[str] | None = None):
        super().__init__()
        self._packs: list[Pack] = list(packs or [])
        self._favorites: set[str] = set(favorites or set())

    # ---- queries ----
    def packs(self) -> list[Pack]:
        return list(self._packs)

    def pack(self, pack_id: str) -> Pack | None:
        return next((p for p in self._packs if p.id == pack_id), None)

    def visible_packs(self) -> list[Pack]:
        return [p for p in self._packs if p.visible]

    def all_stations(self) -> list[Station]:
        return [s for p in self._packs for s in p.stations]

    def is_empty(self) -> bool:
        return not self._packs

    # ---- favourites overlay (by URL) ----
    def is_favorite(self, url: str) -> bool:
        return url in self._favorites

    def favorites_stations(self) -> list[Station]:
        out, seen = [], set()
        for s in self.all_stations():
            if s.url in self._favorites and s.url not in seen:
                seen.add(s.url)
                out.append(s)
        return out

    def set_favorite(self, url: str, on: bool) -> None:
        if on:
            self._favorites.add(url)
        else:
            self._favorites.discard(url)
        self.changed.emit()

    # ---- snapshots ----
    def snapshot(self) -> CatalogMemento:
        return CatalogMemento([p.to_dict() for p in self._packs], sorted(self._favorites))

    def restore(self, memento: CatalogMemento) -> None:
        self._packs = memento.packs()
        self._favorites = memento.favorites()
        self.changed.emit()

    # ---- mutations (used by commands) ----
    def add_pack(self, pack: Pack) -> None:
        self._packs.append(pack)
        self.changed.emit()

    def remove_pack(self, pack_id: str) -> None:
        self._packs = [p for p in self._packs if p.id != pack_id]
        self.changed.emit()

    def move_pack(self, pack_id: str, delta: int) -> None:
        i = next((n for n, p in enumerate(self._packs) if p.id == pack_id), -1)
        j = i + delta
        if i >= 0 and 0 <= j < len(self._packs):
            self._packs[i], self._packs[j] = self._packs[j], self._packs[i]
            self.changed.emit()

    def set_pack_stations(self, pack_id: str, stations: list[Station]) -> None:
        p = self.pack(pack_id)
        if p is not None and not p.is_managed:  # curated packs are read-only
            p.stations = list(stations)
            self.changed.emit()

    def rename_pack(self, pack_id: str, name: str) -> None:
        p = self.pack(pack_id)
        if p is not None and not p.is_managed:
            p.name = name
            self.changed.emit()

    def set_visible(self, pack_id: str, visible: bool) -> None:
        p = self.pack(pack_id)
        if p is not None:
            p.visible = visible
            self.changed.emit()

    def replace_managed_pack(self, pack_id: str, name: str, stations: list[Station], version: int) -> None:
        """Update a curated pack by replacing it wholesale with the remote content."""
        p = self.pack(pack_id)
        if p is not None:
            p.name = name
            p.stations = list(stations)
            p.source_version = version
            self.changed.emit()

    def clone_pack(self, pack_id: str) -> Pack | None:
        """Copy a pack into a new, fully-editable user pack (no source link)."""
        src = self.pack(pack_id)
        if src is None:
            return None
        clone = Pack(
            id=self._unique_id(_slug(src.name) + "-copy"),
            name=f"{src.name} (copy)",
            visible=True,
            stations=[Station.from_dict(s.to_dict()) for s in src.stations],
        )
        self._packs.append(clone)
        self.changed.emit()
        return clone

    def move_station_at(self, from_pack_id: str, index: int, to_pack_id: str) -> None:
        src = self.pack(from_pack_id)
        dest = self.pack(to_pack_id)
        if src and dest and not dest.is_managed and 0 <= index < len(src.stations):
            dest.stations.append(src.stations.pop(index))
            self.changed.emit()

    def _unique_id(self, base: str) -> str:
        existing = {p.id for p in self._packs}
        pid, n = base, 2
        while pid in existing:
            pid, n = f"{base}-{n}", n + 1
        return pid

    # ---- serialisation ----
    @classmethod
    def from_dict(cls, obj: dict) -> "Catalog":
        return cls(
            [Pack.from_dict(p) for p in obj.get("packs", [])],
            {str(u) for u in obj.get("favorites", [])},
        )

    def to_dict(self) -> dict:
        return {
            "version": self.VERSION,
            "favorites": sorted(self._favorites),
            "packs": [p.to_dict() for p in self._packs],
        }


def _slug(name) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in str(name)).strip("-") or "pack"
