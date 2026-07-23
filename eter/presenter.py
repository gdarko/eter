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


class _MainWindow(QWidget):
    """Top-level window that asks a callback what closing should do.

    ``on_close()`` returns True to let the window close (quit the app) or False to
    keep the app running and hide the window (minimize to tray).
    """

    def __init__(self, on_close):
        super().__init__()
        self._on_close = on_close

    def closeEvent(self, event):  # noqa: N802 - Qt override
        if self._on_close():
            super().closeEvent(event)
        else:
            event.ignore()
            self.hide()


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
    """A desktop window hosting the shared PlayerPanel, with a best-effort tray.

    Where the desktop has a tray, closing the window minimizes to it (Show/Quit in
    the tray menu); where it does not, closing the window quits — so the app is
    never left running invisibly.
    """

    def __init__(self, app):
        super().__init__(app)
        self._closing = False

        self.window = _MainWindow(self._on_window_close)
        self.window.setObjectName("panelWindow")
        self.window.setWindowTitle("eter")
        self.window.setWindowIcon(icons.tray_icon(active=False))
        lay = QVBoxLayout(self.window)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = PlayerPanel(app)
        lay.addWidget(self.panel)
        self.window.resize(theme.MENU_WIDTH, 540)

        # Best-effort tray for minimize-to-tray (only where the desktop has one).
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(app)
            self.tray.setIcon(icons.tray_icon(active=False))
            self.tray.setToolTip("eter")
            menu = QMenu()
            show_action = QAction("Show eter", menu)
            show_action.triggered.connect(self._show_window)
            menu.addAction(show_action)
            menu.addSeparator()
            quit_action = QAction("Quit eter", menu)
            quit_action.triggered.connect(app.quit)
            menu.addAction(quit_action)
            # setContextMenu so the menu works on Linux SNI/DBus (no click activation).
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._on_tray_activated)
            self._tray_menu = menu  # keep a reference alive

    def start(self) -> None:
        self.rebuild()
        if self.tray is not None:
            self.tray.show()
        self._show_window()

    def _show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _on_tray_activated(self, reason) -> None:
        R = QSystemTrayIcon.ActivationReason
        if reason in (R.Trigger, R.DoubleClick):
            self._show_window()

    def _on_window_close(self) -> bool:
        """closeEvent hook: True closes (quits), False hides to tray."""
        if self._closing:
            return True
        if self.tray is not None:
            return False  # minimize to tray; the app keeps running
        self._closing = True
        self.app.quit()  # no tray to fall back to: closing the window quits
        return True

    def rebuild(self) -> None:
        self.panel.rebuild()

    def set_active(self, active: bool) -> None:
        if self.tray is not None:
            self.tray.setIcon(icons.tray_icon(active=active))

    def update_status(self) -> None:
        text = self.app._np_text() if self.app.current else "eter"
        self.window.setWindowTitle(text)
        if self.tray is not None:
            self.tray.setToolTip(f"eter — {text}" if self.app.current else "eter")

    def sync_active(self) -> None:
        self.panel.sync_active()

    def notify(self, title: str, message: str, level: str = "info") -> None:
        self.panel.set_status(message)

    def apply_theme(self) -> None:
        self.panel.apply_theme()

    def update_sleep_label(self) -> None:
        self.panel.update_sleep_label()

    def shutdown(self) -> None:
        self._closing = True
        self.window.hide()
        if self.tray is not None:
            self.tray.hide()


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
