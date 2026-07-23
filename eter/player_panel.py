"""The windowed player view: the shared now-playing header + a station tree.

Used by WindowPresenter on Linux / when there is no system tray. It reuses the
same NowPlayingHeader widget the tray popup uses, so play/stop, volume, the
waveform, and now-playing all come for free; it adds a station tree and a small
footer (Settings / Sleep / Quit) for what the tray menu would otherwise carry.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import config, theme

_STATION_ROLE = Qt.ItemDataRole.UserRole


class PlayerPanel(QWidget):
    """Composes the shared header + a catalog station tree + footer controls."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("panel")
        self.setMinimumWidth(theme.MENU_WIDTH)
        self._station_items: list[tuple[object, QTreeWidgetItem]] = []
        self._sleep_actions: list[tuple[int, QAction]] = []
        self._build()
        self.apply_theme()

    # ---- construction ----
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        root.addWidget(self.app.header)  # reparents the shared now-playing header here

        self.tree = QTreeWidget()
        self.tree.setObjectName("stations")
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.itemClicked.connect(self._on_item)
        self.tree.itemActivated.connect(self._on_item)
        root.addWidget(self.tree, 1)

        self.status = QLabel("")
        self.status.setObjectName("panelStatus")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addWidget(self._button("Settings…", self.app.open_settings))
        footer.addWidget(self._sleep_button())
        footer.addStretch(1)
        footer.addWidget(self._button("Quit", self.app.quit))
        root.addLayout(footer)

    def _button(self, text: str, slot) -> QToolButton:
        b = QToolButton()
        b.setObjectName("panelBtn")
        b.setText(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False: slot())
        return b

    def _sleep_button(self) -> QToolButton:
        b = QToolButton()
        b.setObjectName("panelBtn")
        b.setText("Sleep")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(b)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for minutes, label in config.SLEEP_OPTIONS:
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setActionGroup(group)
            act.setChecked(minutes == self.app._sleep_minutes)
            act.triggered.connect(lambda _=False, m=minutes: self.app._set_sleep(m))
            menu.addAction(act)
            self._sleep_actions.append((minutes, act))
        b.setMenu(menu)
        return b

    # ---- public API (mirrors what the presenter needs) ----
    def rebuild(self) -> None:
        self.tree.clear()
        self._station_items = []
        cat = self.app.catalog

        favorites = cat.favorites_stations()
        if favorites:
            node = QTreeWidgetItem(self.tree, ["★  Favorites"])
            node.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for st in favorites:
                self._add_station(node, st)
            node.setExpanded(True)

        for pack in cat.visible_packs():
            if not pack.stations:
                continue
            pack_node = QTreeWidgetItem(self.tree, [pack.name])
            pack_node.setFlags(Qt.ItemFlag.ItemIsEnabled)
            groups = pack.groups()
            if len(groups) <= 1:
                for st in pack.stations:
                    self._add_station(pack_node, st)
            else:
                for grp in groups:
                    gnode = QTreeWidgetItem(pack_node, [grp.name])
                    gnode.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    for st in grp.stations:
                        self._add_station(gnode, st)
            pack_node.setExpanded(True)

        self.sync_active()
        if self.app._update_info is not None:
            self.set_status(f"Update available: {self.app._update_info[0]}")

    def _add_station(self, parent: QTreeWidgetItem, st) -> None:
        if not st.url.strip():  # skip placeholder rows from the editor
            return
        item = QTreeWidgetItem(parent, [st.name])
        item.setData(0, _STATION_ROLE, st)
        self._station_items.append((st, item))

    def _on_item(self, item: QTreeWidgetItem, _col: int = 0) -> None:
        st = item.data(0, _STATION_ROLE)
        if st is not None:
            self.app.play_station(st)

    def sync_active(self) -> None:
        for st, item in self._station_items:
            active = self.app._is_current(st)
            font = item.font(0)
            font.setBold(active)
            item.setFont(0, font)
            item.setText(0, ("▶  " if active else "") + st.name)

    def set_status(self, text: str) -> None:
        self.status.setText(text or "")

    def update_sleep_label(self) -> None:
        for minutes, act in self._sleep_actions:
            act.setChecked(minutes == self.app._sleep_minutes)

    def apply_theme(self) -> None:
        self.setStyleSheet(theme.panel_qss(self.app._palette))
        self.app.header.apply_palette(self.app._palette)
