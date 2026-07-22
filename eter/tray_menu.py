"""Platform tray-menu presentation (Strategy).

The tray behaves differently per platform: macOS/Windows deliver click
activation, so we pop the menu up ourselves and show the rich now-playing header
widget; modern Linux drives the tray over DBus (StatusNotifierItem/AppIndicator),
which never delivers ``activated`` and cannot render a ``QWidgetAction`` widget, so
the menu must be registered with ``setContextMenu`` and the header controls offered
as plain menu items. Each strategy encapsulates install + now-playing rendering +
on-open refresh; ``TrayApp`` (the Mediator) just delegates.
"""
from __future__ import annotations

import sys
from abc import ABC, abstractmethod

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QActionGroup, QCursor
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

_ACTIVE = ("connecting", "buffering", "playing", "reconnecting")
_VOLUME_STEPS = [(0, "Mute"), (25, "25%"), (50, "50%"), (75, "75%"), (100, "100%")]


class TrayMenuStrategy(ABC):
    """How the tray shows its menu and its now-playing controls."""

    def __init__(self, app):
        self.app = app  # the TrayApp collaborator (used read-only + its handlers)

    @abstractmethod
    def install(self, tray: QSystemTrayIcon, menu: QMenu) -> None:
        """Wire the tray icon so a click reveals ``menu``."""

    @abstractmethod
    def build_now_playing(self, menu: QMenu) -> None:
        """Add the now-playing area at the top of a freshly (re)built menu."""

    def refresh(self) -> None:
        """Update dynamic bits right before the menu is shown (default: nothing)."""


class PopupTrayMenu(TrayMenuStrategy):
    """macOS/Windows: pop the menu up on activation; show the rich header widget."""

    def install(self, tray: QSystemTrayIcon, menu: QMenu) -> None:
        self._tray = tray
        self._menu = menu
        tray.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        # We render the menu ourselves (not the native tray menu) so the custom
        # header widget renders and the waveform animates.
        R = QSystemTrayIcon.ActivationReason
        if reason in (R.Trigger, R.Context):
            # Defer to the next event-loop turn: popping up synchronously inside
            # the click handler lets the mouse release fall through onto the menu
            # on Windows, which can land on "Quit" and close the app.
            QTimer.singleShot(0, self._show_menu)

    def _show_menu(self) -> None:
        rect = self._tray.geometry()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            self._menu.popup(rect.bottomLeft())
        else:
            self._menu.popup(QCursor.pos())

    def build_now_playing(self, menu: QMenu) -> None:
        menu.addAction(self.app.header_action)


class NativeTrayMenu(TrayMenuStrategy):
    """Linux (DBus): register a context menu; offer header controls as items."""

    def install(self, tray: QSystemTrayIcon, menu: QMenu) -> None:
        tray.setContextMenu(menu)

    def build_now_playing(self, menu: QMenu) -> None:
        self._now = QAction(self.app._np_text(), menu)
        self._now.setEnabled(False)  # non-interactive status line
        menu.addAction(self._now)

        self._toggle = QAction(self._toggle_label(), menu)
        self._toggle.setEnabled(self._toggle_enabled())
        self._toggle.triggered.connect(lambda _=False: self.app._toggle_play())
        menu.addAction(self._toggle)

        vol_menu = menu.addMenu("Volume")
        grp = QActionGroup(vol_menu)
        grp.setExclusive(True)
        self._vol_actions: list[tuple[int, QAction]] = []
        closest = self._closest_step()
        for level, label in _VOLUME_STEPS:
            act = QAction(label, vol_menu)
            act.setCheckable(True)
            act.setActionGroup(grp)
            act.setChecked(level == closest)
            act.triggered.connect(lambda _=False, v=level: self.app._on_volume(v))
            vol_menu.addAction(act)
            self._vol_actions.append((level, act))

    def refresh(self) -> None:
        # Reflect state/volume that may have changed since the menu was built.
        if getattr(self, "_now", None) is None:
            return
        self._now.setText(self.app._np_text())
        self._toggle.setText(self._toggle_label())
        self._toggle.setEnabled(self._toggle_enabled())
        closest = self._closest_step()
        for level, act in self._vol_actions:
            act.setChecked(level == closest)

    # ---- helpers ----
    def _toggle_label(self) -> str:
        return "Stop" if self.app.state in _ACTIVE else "Play"

    def _toggle_enabled(self) -> bool:
        return self.app.state in _ACTIVE or self.app.current is not None

    def _closest_step(self) -> int:
        cur = int(round(self.app._volume * 100))
        return min((s for s, _ in _VOLUME_STEPS), key=lambda s: abs(s - cur))


def make_tray_menu(app) -> TrayMenuStrategy:
    """Pick the tray-menu strategy for the current platform."""
    if sys.platform.startswith("linux"):
        return NativeTrayMenu(app)
    return PopupTrayMenu(app)
