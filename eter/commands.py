"""Editor operations as commands with undo/redo (Command + Memento).

Each command snapshots the catalog before it applies (Memento) and restores that
snapshot to undo. A CommandStack drives the editor's Undo/Redo.
"""
from __future__ import annotations

from .catalog import Catalog, Pack, Station, _slug

__all__ = [
    "Command", "CommandStack", "CreatePack", "RenamePack", "DeletePack",
    "SetVisible", "MovePack", "SetPackStations", "MoveStation",
    "UpdatePack", "AddPack", "ClonePack", "ToggleFavorite",
]


class Command:
    label = "edit"

    def execute(self) -> None:
        raise NotImplementedError

    def undo(self) -> None:
        raise NotImplementedError


class CatalogCommand(Command):
    """Snapshot-based command: capture state, apply, restore to undo."""

    def __init__(self, catalog: Catalog):
        self._catalog = catalog
        self._before = None

    def execute(self) -> None:
        self._before = self._catalog.snapshot()
        self._apply()

    def undo(self) -> None:
        if self._before is not None:
            self._catalog.restore(self._before)

    def _apply(self) -> None:
        raise NotImplementedError


class CreatePack(CatalogCommand):
    label = "Create pack"

    def __init__(self, catalog: Catalog, name: str):
        super().__init__(catalog)
        self._name = name

    def _apply(self) -> None:
        existing = {p.id for p in self._catalog.packs()}
        base = _slug(self._name)
        pid, n = base, 2
        while pid in existing:
            pid, n = f"{base}-{n}", n + 1
        self._catalog.add_pack(Pack(id=pid, name=self._name, visible=True, stations=[]))


class RenamePack(CatalogCommand):
    label = "Rename pack"

    def __init__(self, catalog: Catalog, pack_id: str, name: str):
        super().__init__(catalog)
        self._id, self._name = pack_id, name

    def _apply(self) -> None:
        self._catalog.rename_pack(self._id, self._name)


class DeletePack(CatalogCommand):
    label = "Delete pack"

    def __init__(self, catalog: Catalog, pack_id: str):
        super().__init__(catalog)
        self._id = pack_id

    def _apply(self) -> None:
        self._catalog.remove_pack(self._id)


class SetVisible(CatalogCommand):
    label = "Toggle pack visibility"

    def __init__(self, catalog: Catalog, pack_id: str, visible: bool):
        super().__init__(catalog)
        self._id, self._visible = pack_id, visible

    def _apply(self) -> None:
        self._catalog.set_visible(self._id, self._visible)


class MovePack(CatalogCommand):
    label = "Reorder pack"

    def __init__(self, catalog: Catalog, pack_id: str, delta: int):
        super().__init__(catalog)
        self._id, self._delta = pack_id, delta

    def _apply(self) -> None:
        self._catalog.move_pack(self._id, self._delta)


class SetPackStations(CatalogCommand):
    """Replace a pack's station list (covers add / remove / edit / reorder)."""

    label = "Edit stations"

    def __init__(self, catalog: Catalog, pack_id: str, stations: list[Station]):
        super().__init__(catalog)
        self._id, self._stations = pack_id, stations

    def _apply(self) -> None:
        self._catalog.set_pack_stations(self._id, self._stations)


class MoveStation(CatalogCommand):
    label = "Move station to pack"

    def __init__(self, catalog: Catalog, from_pack_id: str, index: int, to_pack_id: str):
        super().__init__(catalog)
        self._from, self._index, self._to = from_pack_id, index, to_pack_id

    def _apply(self) -> None:
        self._catalog.move_station_at(self._from, self._index, self._to)


class UpdatePack(CatalogCommand):
    """Refresh a curated pack by replacing it wholesale with the remote content."""

    label = "Update pack"

    def __init__(self, catalog: Catalog, pack_id: str, name: str, remote_stations, version: int):
        super().__init__(catalog)
        self._id, self._name = pack_id, name
        self._stations, self._version = remote_stations, version

    def _apply(self) -> None:
        self._catalog.replace_managed_pack(self._id, self._name, self._stations, self._version)


class AddPack(CatalogCommand):
    """Install a new curated pack from remote."""

    label = "Add pack"

    def __init__(self, catalog: Catalog, source_id: str, name: str, version: int, stations):
        super().__init__(catalog)
        self._source_id, self._name, self._version = source_id, name, version
        self._stations = stations

    def _apply(self) -> None:
        self._catalog.add_pack(
            Pack(
                id=self._source_id,
                name=self._name,
                visible=True,
                stations=list(self._stations),
                source_id=self._source_id,
                source_version=self._version,
            )
        )


class ClonePack(CatalogCommand):
    """Copy a pack into a new, fully-editable user pack."""

    label = "Clone pack"

    def __init__(self, catalog: Catalog, pack_id: str):
        super().__init__(catalog)
        self._id = pack_id

    def _apply(self) -> None:
        self._catalog.clone_pack(self._id)


class ToggleFavorite(CatalogCommand):
    """Star / unstar a station by URL (catalog overlay)."""

    label = "Toggle favourite"

    def __init__(self, catalog: Catalog, url: str):
        super().__init__(catalog)
        self._url = url

    def _apply(self) -> None:
        self._catalog.set_favorite(self._url, not self._catalog.is_favorite(self._url))


class CommandStack:
    def __init__(self):
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def do(self, command: Command) -> None:
        command.execute()
        self._undo.append(command)
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if self._undo:
            command = self._undo.pop()
            command.undo()
            self._redo.append(command)

    def redo(self) -> None:
        if self._redo:
            command = self._redo.pop()
            command.execute()
            self._undo.append(command)
