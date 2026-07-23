"""How the app presents itself (Strategy): system tray vs a desktop window.

The tray is second-class on Linux (a DBus menu can't render the rich header, and
some desktops have no tray at all), so the app can present as a small window
instead. Each presenter owns its view (tray+menu or window+panel) and exposes the
same small interface; the TrayApp Mediator drives them uniformly and stays free of
view/platform branching. make_presenter() picks one from preference + platform +
tray availability.
"""
from __future__ import annotations

import sys
from abc import ABC, abstractmethod

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices
from PySide6.QtWidgets import (
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from . import config, display_version, icons, theme
from .menu_builder import TrayMenuBuilder
from .player_panel import PlayerPanel
from .tray_menu import make_tray_menu

_MSG = {
    "warning": QSystemTrayIcon.MessageIcon.Warning,
    "info": QSystemTrayIcon.MessageIcon.Information,
    "none": QSystemTrayIcon.MessageIcon.NoIcon,
}


class Presenter(ABC):
    """A view for the app. Methods are driven by the TrayApp Mediator."""

    def __init__(self, app):
        self.app = app

    @abstractmethod
    def start(self) -> None:
        """Build the view and show it."""

    @abstractmethod
    def rebuild(self) -> None:
        """(Re)build the station list and its surrounding controls."""

    @abstractmethod
    def set_active(self, active: bool) -> None:
        """Reflect whether playback is active (tray icon / window chrome)."""

    @abstractmethod
    def update_status(self) -> None:
        """Refresh the now-playing status line (tooltip / window title)."""

    @abstractmethod
    def sync_active(self) -> None:
        """Highlight the currently playing station."""

    @abstractmethod
    def notify(self, title: str, message: str, level: str = "info") -> None:
        """Surface a transient message (tray balloon / in-window status)."""

    @abstractmethod
    def apply_theme(self) -> None:
        """Restyle to the app's current palette."""

    @abstractmethod
    def update_sleep_label(self) -> None:
        """Refresh the sleep-timer control to the current state."""

    @abstractmethod
    def shutdown(self) -> None:
        """Tear the view down on quit."""


class TrayPresenter(Presenter):
    """System-tray icon + styled popup menu (macOS menu bar, Windows tray)."""

    def __init__(self, app):
        super().__init__(app)
        self.tray = QSystemTrayIcon(app)
        self.tray.setIcon(icons.tray_icon(active=False))
        self.tray.setToolTip("eter — stopped")

        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.update_sleep_label)

        # Platform tray-menu presentation (Strategy): popup+header on mac/win,
        # native context menu on Linux (DBus tray can't render the header widget).
        self._tray_menu = make_tray_menu(app)
        self._tray_menu.install(self.tray, self.menu)
        self.menu.aboutToShow.connect(self._tray_menu.refresh)

        # The header widget is shared/owned by the controller; the tray wraps it in
        # a QWidgetAction (tray-only) and exposes it for the tray-menu strategy.
        self.header_action = QWidgetAction(app)
        self.header_action.setDefaultWidget(app.header)
        app.header_action = self.header_action

        self._station_group: QActionGroup | None = None
        self._station_actions: list = []
        self._sleep_menu: QMenu | None = None
        self._sleep_actions: list[tuple[int, QAction]] = []

    def start(self) -> None:
        self.rebuild()
        self.tray.show()

    def rebuild(self) -> None:
        app = self.app
        self.menu.clear()
        qss = theme.menu_qss(app._palette)
        self.menu.setStyleSheet(qss)
        self._station_group = QActionGroup(self.menu)
        self._station_group.setExclusive(True)

        self._tray_menu.build_now_playing(self.menu)
        self.menu.addSeparator()

        builder = TrayMenuBuilder(app.catalog, qss, app.play_station, app._is_current)
        builder.build_into(self.menu, self._station_group)
        self._station_actions = builder.station_actions
        self.menu.addSeparator()

        self._sleep_menu = self.menu.addMenu(app._sleep_title())
        self._sleep_menu.setStyleSheet(qss)
        sleep_group = QActionGroup(self._sleep_menu)
        sleep_group.setExclusive(True)
        self._sleep_actions = []
        for minutes, label in config.SLEEP_OPTIONS:
            act = QAction(label, self._sleep_menu)
            act.setCheckable(True)
            act.setChecked(minutes == app._sleep_minutes)
            act.setActionGroup(sleep_group)
            act.triggered.connect(lambda _c=False, m=minutes: app._set_sleep(m))
            self._sleep_menu.addAction(act)
            self._sleep_actions.append((minutes, act))
        self.menu.addSeparator()

        if app._update_info is not None:
            version, url = app._update_info
            update_action = QAction(f"⬆  Update available: {version}", self.menu)
            update_action.triggered.connect(
                lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u))
            )
            self.menu.addAction(update_action)

        self._add_settings_quit()

        app.header.set_state(app.state)
        if app.current is not None:
            app.header.set_station(app.current.name)
            app.header.set_title(app.current_title)

    def _add_settings_quit(self) -> None:
        app = self.app
        settings_action = QAction("Settings…", self.menu)
        settings_action.triggered.connect(app.open_settings)
        self.menu.addAction(settings_action)

        check_action = QAction("Check for Updates…", self.menu)
        check_action.triggered.connect(app._check_updates_manual)
        self.menu.addAction(check_action)

        quit_action = QAction("Quit eter", self.menu)
        quit_action.triggered.connect(app.quit)
        self.menu.addAction(quit_action)

        self.menu.addSeparator()
        version_item = QAction(f"eter {display_version()}", self.menu)
        version_item.setEnabled(False)  # non-interactive version footer
        self.menu.addAction(version_item)

    def set_active(self, active: bool) -> None:
        self.tray.setIcon(icons.tray_icon(active=active))

    def update_status(self) -> None:
        app = self.app
        text = app._np_text()
        self.tray.setToolTip(f"eter — {text}" if app.current else "eter — stopped")

    def sync_active(self) -> None:
        for st, act in self._station_actions:
            act.setChecked(self.app._is_current(st))

    def notify(self, title: str, message: str, level: str = "info") -> None:
        self.tray.showMessage(title, message, _MSG.get(level, _MSG["info"]))

    def apply_theme(self) -> None:
        self.menu.setStyleSheet(theme.menu_qss(self.app._palette))

    def update_sleep_label(self) -> None:
        try:
            if self._sleep_menu is not None:
                self._sleep_menu.setTitle(self.app._sleep_title())
            for minutes, act in self._sleep_actions:
                act.setChecked(minutes == self.app._sleep_minutes)
        except RuntimeError:
            pass  # menu was rebuilt underneath us; the next build refreshes it

    def shutdown(self) -> None:
        self.tray.hide()


class WindowPresenter(Presenter):
    """A small desktop window hosting the shared PlayerPanel (Linux / no tray)."""

    def __init__(self, app):
        super().__init__(app)
        self.window = QWidget()
        self.window.setObjectName("panelWindow")
        self.window.setWindowTitle("eter")
        lay = QVBoxLayout(self.window)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = PlayerPanel(app)
        lay.addWidget(self.panel)
        self.window.resize(theme.MENU_WIDTH, 540)

    def start(self) -> None:
        self.rebuild()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def rebuild(self) -> None:
        self.panel.rebuild()

    def set_active(self, active: bool) -> None:
        pass  # the header already reflects playback state

    def update_status(self) -> None:
        app = self.app
        self.window.setWindowTitle(app._np_text() if app.current else "eter")

    def sync_active(self) -> None:
        self.panel.sync_active()

    def notify(self, title: str, message: str, level: str = "info") -> None:
        self.panel.set_status(message)

    def apply_theme(self) -> None:
        self.panel.apply_theme()

    def update_sleep_label(self) -> None:
        self.panel.update_sleep_label()

    def shutdown(self) -> None:
        self.window.close()


def make_presenter(app) -> Presenter:
    """Pick the presenter from preference -> platform -> tray availability."""
    mode = str(app.settings.value("display_mode", "auto") or "auto").lower()
    has_tray = QSystemTrayIcon.isSystemTrayAvailable()
    if mode == "window":
        return WindowPresenter(app)
    if mode == "tray":
        return TrayPresenter(app) if has_tray else WindowPresenter(app)
    # auto: window on Linux or when there is no tray; tray otherwise
    if not has_tray or sys.platform.startswith("linux"):
        return WindowPresenter(app)
    return TrayPresenter(app)
