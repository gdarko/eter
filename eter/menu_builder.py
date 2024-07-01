"""Assemble the tray menu's catalog section from the catalog (Builder)."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from .catalog import Catalog, Station


class TrayMenuBuilder:
    """Builds Favorites + one submenu per visible pack (nesting sub-groups)."""

    def __init__(
        self,
        catalog: Catalog,
        qss: str,
        on_play: Callable[[Station], None],
        is_current: Callable[[Station], bool],
    ):
        self._catalog = catalog
        self._qss = qss
        self._on_play = on_play
        self._is_current = is_current
        self.station_actions: list[tuple[Station, QAction]] = []

    def build_into(self, menu: QMenu, group: QActionGroup) -> None:
        favorites = self._catalog.favorites_stations()
        if favorites:
            fav_menu = menu.addMenu("★  Favorites")
            fav_menu.setStyleSheet(self._qss)
            for st in favorites:
                self._add(fav_menu, st, group)
            menu.addSeparator()

        for pack in self._catalog.visible_packs():
            if not pack.stations:
                continue
            pack_menu = menu.addMenu(pack.name)
            pack_menu.setStyleSheet(self._qss)
            groups = pack.groups()
            if len(groups) <= 1:
                for st in pack.stations:
                    self._add(pack_menu, st, group)
            else:
                for grp in groups:
                    sub = pack_menu.addMenu(grp.name)
                    sub.setStyleSheet(self._qss)
                    for st in grp.stations:
                        self._add(sub, st, group)

    def _add(self, menu: QMenu, station: Station, group: QActionGroup) -> None:
        if not station.url.strip():  # skip placeholder rows from the editor
            return
        act = QAction(station.name, menu)
        act.setCheckable(True)
        act.setChecked(self._is_current(station))
        act.setActionGroup(group)
        act.triggered.connect(lambda _checked=False, s=station: self._on_play(s))
        menu.addAction(act)
        self.station_actions.append((station, act))
