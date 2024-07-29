"""The tray application controller.

TrayApp is a Mediator: it wires the catalog, player, metadata resolver, menu
builder, and settings together, and translates their signals into UI updates. It
observes the catalog and rebuilds the menu whenever it changes.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QCursor, QDesktopServices
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidgetAction

from . import __version__, config, icons, theme
from .catalog import Catalog, Station
from .catalog_repository import CatalogRepository
from .menu_builder import TrayMenuBuilder
from .metadata import NowPlayingResolver
from .pack_service import RemotePackService
from .player import RadioPlayer
from .settings_dialog import SettingsDialog
from .updater import UpdateChecker
from .widgets import NowPlayingHeader

_ACTIVE_STATES = ("connecting", "buffering", "playing", "reconnecting")

SLEEP_OPTIONS = [
    (0, "Off"),
    (15, "15 minutes"),
    (30, "30 minutes"),
    (45, "45 minutes"),
    (60, "1 hour"),
    (90, "1.5 hours"),
    (120, "2 hours"),
]


class TrayApp(QObject):
    def __init__(self, app: QApplication, catalog: Catalog, repository: CatalogRepository):
        super().__init__()
        self.app = app
        self.catalog = catalog
        self.repository = repository
        self.settings = config.settings()
        self._palette = theme.current()

        self.current: Station | None = None
        self.current_title = ""
        self.state = "stopped"

        self.player = RadioPlayer(self)
        self.nowplaying = NowPlayingResolver(self.player.media_player, self)

        self._volume = float(self.settings.value("volume", 0.8))
        self.player.set_volume(self._volume)
        self.notifications = self._read_bool("notifications", True)

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(icons.tray_icon(active=False))
        self.tray.setToolTip("eter — stopped")
        self.tray.activated.connect(self._on_tray_activated)

        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._update_sleep_label)

        # sleep timer
        self._sleep_minutes = 0
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._on_sleep_fired)
        self._sleep_menu: QMenu | None = None
        self._sleep_actions: list[tuple[int, QAction]] = []

        # now-playing header card (persists across menu rebuilds)
        self.header = NowPlayingHeader(self._palette, width=theme.MENU_WIDTH)
        self.header.playToggled.connect(self._toggle_play)
        self.header.volumeChanged.connect(self._on_volume)
        self.header.set_volume(int(round(self._volume * 100)))
        self.header_action = QWidgetAction(self)
        self.header_action.setDefaultWidget(self.header)

        self.player.stateChanged.connect(self._on_state)
        self.player.errorText.connect(self._on_error)
        self.nowplaying.titleChanged.connect(self._on_title)
        self.catalog.changed.connect(self._build_menu)  # Observer
        try:
            self.app.styleHints().colorSchemeChanged.connect(self._on_theme_changed)
        except Exception:  # noqa: BLE001 - older Qt
            pass

        self._settings_dialog: SettingsDialog | None = None
        self._station_actions: list[tuple[Station, QAction]] = []

        # update checker (notify-only)
        self._update_info: tuple[str, str] | None = None
        self._manual_check = False
        self.updater = UpdateChecker(__version__, parent=self)
        self.updater.updateAvailable.connect(self._on_update_available)
        self.updater.noUpdate.connect(self._on_no_update)
        self.updater.failed.connect(self._on_update_failed)

        # remote curated packs
        self._manifest: list[tuple[str, str, int]] = []
        self._pack_hint_shown = False
        self.pack_service = RemotePackService(parent=self)
        self.pack_service.manifestReady.connect(self._on_manifest)

        self._build_menu()
        self._restore_last_station()
        self.tray.show()

        if self._read_bool("check_updates", True):
            self.updater.check()
        if self._read_bool("check_pack_updates", True):
            self.pack_service.check()

    # ------------------------------------------------------------------ menu
    def _build_menu(self) -> None:
        self.menu.clear()
        qss = theme.menu_qss(self._palette)
        self.menu.setStyleSheet(qss)
        self._station_group = QActionGroup(self.menu)
        self._station_group.setExclusive(True)

        self.menu.addAction(self.header_action)
        self.menu.addSeparator()

        builder = TrayMenuBuilder(self.catalog, qss, self.play_station, self._is_current)
        builder.build_into(self.menu, self._station_group)
        self._station_actions = builder.station_actions
        self.menu.addSeparator()

        self._sleep_menu = self.menu.addMenu(self._sleep_title())
        self._sleep_menu.setStyleSheet(qss)
        sleep_group = QActionGroup(self._sleep_menu)
        sleep_group.setExclusive(True)
        self._sleep_actions = []
        for minutes, label in SLEEP_OPTIONS:
            act = QAction(label, self._sleep_menu)
            act.setCheckable(True)
            act.setChecked(minutes == self._sleep_minutes)
            act.setActionGroup(sleep_group)
            act.triggered.connect(lambda _c=False, m=minutes: self._set_sleep(m))
            self._sleep_menu.addAction(act)
            self._sleep_actions.append((minutes, act))
        self.menu.addSeparator()

        if self._update_info is not None:
            version, url = self._update_info
            update_action = QAction(f"⬆  Update available: {version}", self.menu)
            update_action.triggered.connect(
                lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u))
            )
            self.menu.addAction(update_action)

        self._add_settings_quit()

        self.header.set_state(self.state)
        if self.current is not None:
            self.header.set_station(self.current.name)
            self.header.set_title(self.current_title)

    def _add_settings_quit(self) -> None:
        settings_action = QAction("Settings…", self.menu)
        settings_action.triggered.connect(self.open_settings)
        self.menu.addAction(settings_action)

        check_action = QAction("Check for Updates…", self.menu)
        check_action.triggered.connect(self._check_updates_manual)
        self.menu.addAction(check_action)

        quit_action = QAction("Quit eter", self.menu)
        quit_action.triggered.connect(self.quit)
        self.menu.addAction(quit_action)

    # ------------------------------------------------------------- behaviour
    def _is_current(self, st: Station) -> bool:
        return (
            self.current is not None
            and st.url == self.current.url
            and st.name == self.current.name
        )

    def play_station(self, st: Station) -> None:
        self.current = st
        self.current_title = ""
        self.settings.setValue("last_station", st.key())
        self.header.set_station(st.name)
        self.header.set_title("")
        self.player.play(st.url)
        self.nowplaying.start(st)
        self._sync_checks()
        self._update_tooltip()

    def _toggle_play(self) -> None:
        if self.state in _ACTIVE_STATES:
            self.player.stop()
            self.nowplaying.stop()
        elif self.current is not None:
            self.play_station(self.current)

    def _restore_last_station(self) -> None:
        key = self.settings.value("last_station", "")
        if not key:
            return
        for st in self.catalog.all_stations():
            if st.key() == key:
                if self._read_bool("auto_resume", True):
                    self.play_station(st)
                else:
                    self.current = st
                    self.header.set_station(st.name)
                    self.header.set_state("stopped")
                    self._sync_checks()
                    self._update_tooltip()
                return

    # --------------------------------------------------------------- signals
    def _on_volume(self, v: int) -> None:
        self._volume = v / 100.0
        self.player.set_volume(self._volume)
        self.settings.setValue("volume", self._volume)

    def _on_state(self, state: str) -> None:
        self.state = state
        self.tray.setIcon(icons.tray_icon(active=state in _ACTIVE_STATES))
        self.header.set_state(state)
        self._update_tooltip()

    def _on_error(self, message: str) -> None:
        if self.notifications:
            self.tray.showMessage(
                "eter — playback error", message, QSystemTrayIcon.MessageIcon.Warning
            )

    def _on_title(self, title: str) -> None:
        changed = title and title != self.current_title
        self.current_title = title
        self.header.set_title(title)
        self._update_tooltip()
        if changed and self.notifications and self.current is not None:
            self.tray.showMessage(
                self.current.name, title, QSystemTrayIcon.MessageIcon.NoIcon
            )

    def _on_manifest(self, manifest) -> None:
        self._manifest = [tuple(m) for m in manifest]
        if self._pack_hint_shown or not self.notifications:
            return
        installed = {
            p.source_id: p.source_version for p in self.catalog.packs() if p.source_id
        }
        known = config.known_source_ids()
        has_update = any(
            mid in installed and ver > installed[mid] for mid, _n, ver in self._manifest
        )
        has_new = any(
            mid not in installed and mid not in known for mid, _n, _v in self._manifest
        )
        if has_update or has_new:
            self._pack_hint_shown = True
            self.tray.showMessage(
                "eter", "Station pack updates are available in Settings.",
                QSystemTrayIcon.MessageIcon.Information,
            )

    def _on_theme_changed(self, *_a) -> None:
        self._palette = theme.current()
        self.header.apply_palette(self._palette)
        self.menu.setStyleSheet(theme.menu_qss(self._palette))

    # ----------------------------------------------------------- updates
    def _check_updates_manual(self) -> None:
        self._manual_check = True
        self.updater.check()

    def _on_update_available(self, version: str, url: str) -> None:
        self._update_info = (version, url)
        self._manual_check = False
        self.tray.showMessage(
            "eter — update available",
            f"Version {version} is available. Use “Update available” in the menu.",
            QSystemTrayIcon.MessageIcon.Information,
        )
        self._build_menu()

    def _on_no_update(self) -> None:
        if self._manual_check:
            self.tray.showMessage(
                "eter", "You’re on the latest version.",
                QSystemTrayIcon.MessageIcon.Information,
            )
        self._manual_check = False

    def _on_update_failed(self, message: str) -> None:
        if self._manual_check:
            self.tray.showMessage(
                "eter", message, QSystemTrayIcon.MessageIcon.Warning
            )
        self._manual_check = False

    # ----------------------------------------------------------- sleep timer
    def _set_sleep(self, minutes: int) -> None:
        self._sleep_minutes = minutes
        if minutes <= 0:
            self._sleep_timer.stop()
        else:
            self._sleep_timer.start(minutes * 60 * 1000)
            if self.notifications:
                self.tray.showMessage(
                    "eter",
                    f"Sleep timer set for {self._sleep_remaining_text()}.",
                    QSystemTrayIcon.MessageIcon.NoIcon,
                )
        self._update_sleep_label()

    def _on_sleep_fired(self) -> None:
        self._sleep_minutes = 0
        self.player.stop()
        self.nowplaying.stop()
        self._update_sleep_label()
        if self.notifications:
            self.tray.showMessage(
                "eter", "Sleep timer: playback stopped.",
                QSystemTrayIcon.MessageIcon.NoIcon,
            )

    def _update_sleep_label(self) -> None:
        try:
            if self._sleep_menu is not None:
                self._sleep_menu.setTitle(self._sleep_title())
            for minutes, act in self._sleep_actions:
                act.setChecked(minutes == self._sleep_minutes)
        except RuntimeError:
            pass  # menu was rebuilt underneath us; the next build refreshes it

    def _sleep_title(self) -> str:
        if self._sleep_minutes and self._sleep_timer.isActive():
            return f"Sleep Timer  ({self._sleep_remaining_text()})"
        return "Sleep Timer"

    def _sleep_remaining_text(self) -> str:
        ms = self._sleep_timer.remainingTime()
        if ms <= 0:
            return "off"
        minutes = (ms + 59_999) // 60_000  # round up to the next whole minute
        if minutes >= 60:
            hours, mins = divmod(minutes, 60)
            return f"{hours} h {mins} min" if mins else f"{hours} h"
        return f"{minutes} min"

    # ----------------------------------------------------------- ui refresh
    def _np_text(self) -> str:
        if self.current is None:
            return "No station selected"
        if self.state == "connecting":
            return f"{self.current.name} — connecting…"
        if self.state == "buffering":
            return f"{self.current.name} — buffering…"
        if self.state == "reconnecting":
            return f"{self.current.name} — reconnecting…"
        if self.state in ("stopped", "error"):
            return f"{self.current.name} — stopped"
        if self.current_title:
            return f"{self.current.name} — {self.current_title}"
        return f"{self.current.name} — ♪"

    def _update_tooltip(self) -> None:
        text = self._np_text()
        self.tray.setToolTip(f"eter — {text}" if self.current else "eter — stopped")

    def _sync_checks(self) -> None:
        for st, act in self._station_actions:
            act.setChecked(self._is_current(st))

    # ---------------------------------------------------------------- system
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # We render the menu ourselves (not the native tray menu) so the custom
        # header renders consistently on all platforms.
        R = QSystemTrayIcon.ActivationReason
        if reason in (R.Trigger, R.Context):
            self._popup_menu()

    def _popup_menu(self) -> None:
        rect = self.tray.geometry()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            self.menu.popup(rect.bottomLeft())
        else:
            self.menu.popup(QCursor.pos())

    def open_settings(self) -> None:
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        dlg = SettingsDialog(
            self.catalog, self.settings, self.repository, self.pack_service, self._manifest
        )
        dlg.finished.connect(self._on_settings_closed)
        self._settings_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_settings_closed(self, _result: int) -> None:
        # Catalog edits were applied live (Observer already rebuilt the menu);
        # re-read preferences that may have changed.
        self.notifications = self._read_bool("notifications", True)
        self._volume = float(self.settings.value("volume", self._volume))
        self.player.set_volume(self._volume)
        self.header.set_volume(int(round(self._volume * 100)))
        if self.current is not None and not any(
            self._is_current(st) for st in self.catalog.all_stations()
        ):
            self.current = None
        self._update_tooltip()

    def quit(self) -> None:
        self.player.stop()
        self.nowplaying.stop()
        self.tray.hide()
        self.app.quit()

    # --------------------------------------------------------------- helpers
    def _read_bool(self, key: str, default: bool) -> bool:
        v = self.settings.value(key, default)
        if isinstance(v, str):
            return v.lower() in ("1", "true", "yes", "on")
        return bool(v)
