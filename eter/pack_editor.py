"""Master-detail pack editor.

Left: the packs (with a visibility checkbox). Right: the selected pack's stations.
Curated packs are read-only (Update / Clone only); user packs are fully editable.
Every change is a Command on a CommandStack (undo/redo), and the widget refreshes
itself when the catalog changes (Observer). Favourites are a catalog overlay, so
the Fav column works on curated packs too.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import commands, config, playlist
from .catalog import Catalog, Pack, Station

_COLS = ("Fav", "Name", "URL", "Group")
_URL_ROLE = Qt.ItemDataRole.UserRole
_NP_ROLE = Qt.ItemDataRole.UserRole + 1


class PackEditor(QWidget):
    def __init__(self, catalog: Catalog, service=None, manifest=None, parent=None):
        super().__init__(parent)
        self._catalog = catalog
        self._service = service
        self._manifest: list[tuple[str, str, int]] = list(manifest or [])
        self._stack = commands.CommandStack()
        self._loading = False
        self._build_ui()
        catalog.changed.connect(self._on_catalog_changed)
        if service is not None:
            service.packReady.connect(self._on_pack_fetched)
            service.manifestReady.connect(self._on_manifest)
        self._reload_packs()

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(QLabel("Packs"))
        self.packList = QListWidget()
        self.packList.currentRowChanged.connect(self._on_pack_selected)
        self.packList.itemChanged.connect(self._on_pack_item_changed)
        left.addWidget(self.packList)
        self.newBtn = self._button("New", self._new_pack)
        self.renameBtn = self._button("Rename", self._rename_pack)
        self.deleteBtn = self._button("Delete", self._delete_pack)
        self.cloneBtn = self._button("Clone", self._clone_pack)
        left.addLayout(self._row(self.newBtn, self.renameBtn, self.deleteBtn, self.cloneBtn))
        self.updateBtn = self._button("Update", self._update_selected)
        self.getMoreBtn = self._button("Get more…", self._get_more)
        left.addLayout(self._row(
            self.updateBtn, self.getMoreBtn,
            self._button("↑", lambda: self._move_pack(-1)),
            self._button("↓", lambda: self._move_pack(1)),
        ))
        root.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Stations in this pack"))
        self.table = QTableWidget(0, len(_COLS))
        self.table.setHorizontalHeaderLabels(_COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.itemChanged.connect(self._on_station_edited)
        right.addWidget(self.table)
        self.stationBtns = [
            self._button("Add", self._add_station),
            self._button("Remove", self._remove_station),
            self._button("↑", lambda: self._move_station(-1)),
            self._button("↓", lambda: self._move_station(1)),
            self._button("Import URL…", self._import_url),
            self._button("Move to…", self._move_to_pack),
        ]
        right.addLayout(self._row(*self.stationBtns))

        undo_row = QHBoxLayout()
        undo_row.addStretch(1)
        self.undoBtn = self._button("Undo", self._undo)
        self.redoBtn = self._button("Redo", self._redo)
        undo_row.addWidget(self.undoBtn)
        undo_row.addWidget(self.redoBtn)
        right.addLayout(undo_row)
        root.addLayout(right, 2)

    @staticmethod
    def _button(text, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    @staticmethod
    def _row(*widgets) -> QHBoxLayout:
        row = QHBoxLayout()
        for w in widgets:
            row.addWidget(w)
        return row

    # -------------------------------------------------------------- command
    def _do(self, command) -> None:
        self._stack.do(command)
        self._refresh_undo()

    def _undo(self) -> None:
        self._stack.undo()
        self._refresh_undo()

    def _redo(self) -> None:
        self._stack.redo()
        self._refresh_undo()

    def _refresh_undo(self) -> None:
        self.undoBtn.setEnabled(self._stack.can_undo())
        self.redoBtn.setEnabled(self._stack.can_redo())

    # --------------------------------------------------- refresh on change
    def _on_catalog_changed(self) -> None:
        if not self._loading:
            self._reload_packs()

    # ----------------------------------------------------------------- packs
    def _current_pack(self) -> Pack | None:
        row = self.packList.currentRow()
        packs = self._catalog.packs()
        return packs[row] if 0 <= row < len(packs) else None

    def _reload_packs(self) -> None:
        self._loading = True
        prev = self.packList.currentRow()
        self.packList.clear()
        for p in self._catalog.packs():
            text = p.name + ("   ⬆ update" if self._pack_has_update(p) else "")
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if p.visible else Qt.CheckState.Unchecked
            )
            self.packList.addItem(item)
        if self.packList.count():
            self.packList.setCurrentRow(min(max(prev, 0), self.packList.count() - 1))
        self._loading = False
        self._reload_stations()
        self._refresh_buttons()

    def _on_pack_selected(self, _row: int) -> None:
        if not self._loading:
            self._reload_stations()
            self._refresh_buttons()

    def _on_pack_item_changed(self, item: QListWidgetItem) -> None:
        if self._loading:
            return
        row = self.packList.row(item)
        packs = self._catalog.packs()
        if 0 <= row < len(packs):
            visible = item.checkState() == Qt.CheckState.Checked
            if visible != packs[row].visible:
                self._do(commands.SetVisible(self._catalog, packs[row].id, visible))

    def _new_pack(self) -> None:
        name, ok = QInputDialog.getText(self, "New pack", "Pack name:")
        if ok and name.strip():
            self._do(commands.CreatePack(self._catalog, name.strip()))

    def _rename_pack(self) -> None:
        p = self._current_pack()
        if not p or p.is_managed:
            return
        name, ok = QInputDialog.getText(self, "Rename pack", "Name:", text=p.name)
        if ok and name.strip():
            self._do(commands.RenamePack(self._catalog, p.id, name.strip()))

    def _delete_pack(self) -> None:
        p = self._current_pack()
        if p:
            self._do(commands.DeletePack(self._catalog, p.id))

    def _clone_pack(self) -> None:
        p = self._current_pack()
        if p:
            self._do(commands.ClonePack(self._catalog, p.id))

    def _move_pack(self, delta: int) -> None:
        p = self._current_pack()
        if p:
            self._do(commands.MovePack(self._catalog, p.id, delta))

    # -------------------------------------------------------------- stations
    def _reload_stations(self) -> None:
        self._loading = True
        self.table.setRowCount(0)
        p = self._current_pack()
        if p:
            for st in p.stations:
                self._append_row(st, p.is_managed)
        self._loading = False

    def _append_row(self, st: Station, managed: bool) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        fav = QTableWidgetItem()
        fav.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        fav.setCheckState(
            Qt.CheckState.Checked if self._catalog.is_favorite(st.url) else Qt.CheckState.Unchecked
        )
        fav.setData(_URL_ROLE, st.url)
        self.table.setItem(row, 0, fav)
        cell_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not managed:
            cell_flags |= Qt.ItemFlag.ItemIsEditable
        for col, value in ((1, st.name), (2, st.url), (3, st.group)):
            item = QTableWidgetItem(value)
            item.setFlags(cell_flags)
            if col == 1:
                item.setData(_NP_ROLE, st.now_playing)  # preserve web spec
            self.table.setItem(row, col, item)

    def _read_table(self) -> list[Station]:
        out: list[Station] = []
        for r in range(self.table.rowCount()):
            name = self._cell(r, 1)
            url = self._cell(r, 2)
            group = self._cell(r, 3) or "General"
            np = self.table.item(r, 1).data(_NP_ROLE)
            out.append(
                Station(
                    name=name or url or "Untitled",
                    url=url,
                    group=group,
                    now_playing=np if isinstance(np, dict) else None,
                )
            )
        return out

    def _cell(self, r: int, c: int) -> str:
        item = self.table.item(r, c)
        return item.text().strip() if item else ""

    def _commit_stations(self) -> None:
        p = self._current_pack()
        if p and not p.is_managed:
            self._do(commands.SetPackStations(self._catalog, p.id, self._read_table()))

    def _on_station_edited(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        if item.column() == 0:  # favourite toggled (works for curated packs too)
            url = item.data(_URL_ROLE)
            if url:
                self._do(commands.ToggleFavorite(self._catalog, url))
            return
        self._commit_stations()

    def _add_station(self) -> None:
        p = self._current_pack()
        if not p or p.is_managed:
            return
        stations = self._read_table()
        stations.append(Station(name="New station", url="http://", group="General"))
        self._do(commands.SetPackStations(self._catalog, p.id, stations))

    def _remove_station(self) -> None:
        r = self.table.currentRow()
        p = self._current_pack()
        if r < 0 or not p or p.is_managed:
            return
        stations = self._read_table()
        del stations[r]
        self._do(commands.SetPackStations(self._catalog, p.id, stations))

    def _move_station(self, delta: int) -> None:
        r = self.table.currentRow()
        p = self._current_pack()
        j = r + delta
        if r < 0 or not p or p.is_managed or not (0 <= j < self.table.rowCount()):
            return
        stations = self._read_table()
        stations[r], stations[j] = stations[j], stations[r]
        self._do(commands.SetPackStations(self._catalog, p.id, stations))
        self.table.selectRow(j)

    def _import_url(self) -> None:
        p = self._current_pack()
        if not p or p.is_managed:
            return
        url, ok = QInputDialog.getText(
            self, "Import station", "Stream or playlist URL (.pls/.m3u ok):"
        )
        url = url.strip()
        if not ok or not url:
            return
        try:
            resolved = playlist.resolve_playlist(url, timeout=6.0)
        except Exception:  # noqa: BLE001
            resolved = url
        stations = self._read_table()
        stations.append(
            Station(name=url.split("//")[-1].split("/")[0], url=resolved, group="General")
        )
        self._do(commands.SetPackStations(self._catalog, p.id, stations))

    def _move_to_pack(self) -> None:
        r = self.table.currentRow()
        src = self._current_pack()
        if r < 0 or not src or src.is_managed:
            return
        menu = QMenu(self)
        for target in self._catalog.packs():
            if target.id == src.id or target.is_managed:
                continue  # can only move into an editable pack
            act = menu.addAction(target.name)
            act.triggered.connect(
                lambda _c=False, tid=target.id: self._do(
                    commands.MoveStation(self._catalog, src.id, r, tid)
                )
            )
        if menu.actions():
            menu.exec(QCursor.pos())

    # ----------------------------------------------------------- remote packs
    def _manifest_version(self, source_id: str | None) -> int | None:
        if not source_id:
            return None
        return next((v for mid, _n, v in self._manifest if mid == source_id), None)

    def _pack_has_update(self, pack: Pack | None) -> bool:
        v = self._manifest_version(pack.source_id) if pack else None
        return v is not None and v > pack.source_version

    def _installed_source_ids(self) -> set[str]:
        return {p.source_id for p in self._catalog.packs() if p.source_id}

    def _available_packs(self) -> list[tuple[str, str, int]]:
        installed = self._installed_source_ids()
        return [m for m in self._manifest if m[0] not in installed]

    def _refresh_buttons(self) -> None:
        p = self._current_pack()
        editable = p is not None and not p.is_managed
        self.renameBtn.setEnabled(editable)
        for b in self.stationBtns:
            b.setEnabled(editable)
        self.cloneBtn.setEnabled(p is not None)
        self.deleteBtn.setEnabled(p is not None)
        self.updateBtn.setEnabled(self._service is not None and self._pack_has_update(p))
        self.getMoreBtn.setEnabled(self._service is not None and bool(self._available_packs()))

    def _on_manifest(self, manifest: list) -> None:
        self._manifest = [tuple(m) for m in manifest]
        self._reload_packs()

    def _update_selected(self) -> None:
        p = self._current_pack()
        if self._service is not None and self._pack_has_update(p):
            self._service.fetch_pack(p.source_id)

    def _get_more(self) -> None:
        if self._service is None:
            return
        known = config.known_source_ids()
        menu = QMenu(self)
        for mid, name, _ver in self._available_packs():
            label = name + ("   (new)" if mid not in known else "")
            act = menu.addAction(label)
            act.triggered.connect(lambda _c=False, m=mid: self._service.fetch_pack(m))
        if menu.actions():
            menu.exec(QCursor.pos())

    def _on_pack_fetched(self, source_id: str, name: str, version: int, stations: list) -> None:
        installed = next(
            (p for p in self._catalog.packs() if p.source_id == source_id), None
        )
        if installed is not None:
            self._do(commands.UpdatePack(self._catalog, installed.id, name, stations, version))
        else:
            self._do(commands.AddPack(self._catalog, source_id, name, version, stations))
            config.add_known_source_ids([source_id])
