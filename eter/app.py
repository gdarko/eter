"""The application controller.

TrayApp is a Mediator: it wires the catalog, player, metadata resolver, and
settings together and translates their signals into UI updates. It observes the
catalog and drives a Presenter (tray popup or desktop window) for all view work,
so it carries no view/platform branching itself.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from . import __version__, config, theme
from .catalog import Catalog, Station
from .catalog_repository import CatalogRepository
from .metadata import NowPlayingResolver
from .pack_service import RemotePackService
from .player import RadioPlayer
from .presenter import make_presenter
from .settings_dialog import SettingsDialog
from .updater import UpdateChecker
from .widgets import NowPlayingHeader

_ACTIVE_STATES = ("connecting", "buffering", "playing", "reconnecting")


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

        # sleep timer
        self._sleep_minutes = 0
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._on_sleep_fired)

        # now-playing header card (shared by whichever presenter is active)
        self.header = NowPlayingHeader(self._palette, width=theme.MENU_WIDTH)
        self.header.playToggled.connect(self._toggle_play)
        self.header.volumeChanged.connect(self._on_volume)
        self.header.set_volume(int(round(self._volume * 100)))
        self.header_action = None  # created by TrayPresenter when the tray is used

        self._settings_dialog: SettingsDialog | None = None

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

        # presentation (Strategy): tray on macOS/Windows, window on Linux / no tray
        self._presenter = make_presenter(self)

        self.player.stateChanged.connect(self._on_state)
        self.player.errorText.connect(self._on_error)
        self.player.audioLevel.connect(self.header.push_level)
        self.nowplaying.titleChanged.connect(self._on_title)
        self.catalog.changed.connect(self._presenter.rebuild)  # Observer
        try:
            self.app.styleHints().colorSchemeChanged.connect(self._on_theme_changed)
        except Exception:  # noqa: BLE001 - older Qt
            pass

        self._presenter.start()
        self._restore_last_station()

        if self._read_bool("check_updates", True):
            self.updater.check()
        if self._read_bool("check_pack_updates", True):
            self.pack_service.check()

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
        self._presenter.sync_active()
        self._presenter.update_status()

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
                    self._presenter.sync_active()
                    self._presenter.update_status()
                return

    # --------------------------------------------------------------- signals
    def _on_volume(self, v: int) -> None:
        self._volume = v / 100.0
        self.player.set_volume(self._volume)
        self.settings.setValue("volume", self._volume)

    def _on_state(self, state: str) -> None:
        self.state = state
        self._presenter.set_active(state in _ACTIVE_STATES)
        self.header.set_state(state)
        self._presenter.update_status()

    def _on_error(self, message: str) -> None:
        if self.notifications:
            self._presenter.notify("eter — playback error", message, "warning")

    def _on_title(self, title: str) -> None:
        changed = title and title != self.current_title
        self.current_title = title
        self.header.set_title(title)
        self._presenter.update_status()
        if changed and self.notifications and self.current is not None:
            self._presenter.notify(self.current.name, title, "none")

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
            self._presenter.notify(
                "eter", "Station pack updates are available in Settings.", "info"
            )

    def _on_theme_changed(self, *_a) -> None:
        self._palette = theme.current()
        self.header.apply_palette(self._palette)
        self._presenter.apply_theme()

    # ----------------------------------------------------------- updates
    def _check_updates_manual(self) -> None:
        self._manual_check = True
        self.updater.check()

    def _on_update_available(self, version: str, url: str) -> None:
        self._update_info = (version, url)
        self._manual_check = False
        self._presenter.notify(
            "eter — update available", f"Version {version} is available.", "info"
        )
        self._presenter.rebuild()

    def _on_no_update(self) -> None:
        if self._manual_check:
            self._presenter.notify("eter", "You’re on the latest version.", "info")
        self._manual_check = False

    def _on_update_failed(self, message: str) -> None:
        if self._manual_check:
            self._presenter.notify("eter", message, "warning")
        self._manual_check = False

    # ----------------------------------------------------------- sleep timer
    def _set_sleep(self, minutes: int) -> None:
        self._sleep_minutes = minutes
        if minutes <= 0:
            self._sleep_timer.stop()
        else:
            self._sleep_timer.start(minutes * 60 * 1000)
            if self.notifications:
                self._presenter.notify(
                    "eter", f"Sleep timer set for {self._sleep_remaining_text()}.", "none"
                )
        self._presenter.update_sleep_label()

    def _on_sleep_fired(self) -> None:
        self._sleep_minutes = 0
        self.player.stop()
        self.nowplaying.stop()
        self._presenter.update_sleep_label()
        if self.notifications:
            self._presenter.notify("eter", "Sleep timer: playback stopped.", "none")

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

    # ---------------------------------------------------------------- system
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
        # Catalog edits were applied live (Observer already rebuilt the view);
        # re-read preferences that may have changed.
        self.notifications = self._read_bool("notifications", True)
        self._volume = float(self.settings.value("volume", self._volume))
        self.player.set_volume(self._volume)
        self.header.set_volume(int(round(self._volume * 100)))
        if self.current is not None and not any(
            self._is_current(st) for st in self.catalog.all_stations()
        ):
            self.current = None
        self._presenter.update_status()

    def quit(self) -> None:
        self.player.stop()
        self.nowplaying.stop()
        self._presenter.shutdown()
        self.app.quit()

    # --------------------------------------------------------------- helpers
    def _read_bool(self, key: str, default: bool) -> bool:
        v = self.settings.value(key, default)
        if isinstance(v, str):
            return v.lower() in ("1", "true", "yes", "on")
        return bool(v)
