"""Tabbed settings: a pack editor and app preferences."""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import autostart
from .catalog import Catalog
from .catalog_repository import CatalogRepository
from .pack_editor import PackEditor


class SettingsDialog(QDialog):
    """Edits the catalog live (revert on cancel, persist on save)."""

    def __init__(
        self,
        catalog: Catalog,
        settings: QSettings,
        repository: CatalogRepository,
        pack_service=None,
        manifest=None,
        parent=None,
    ):
        super().__init__(parent)
        self._catalog = catalog
        self._settings = settings
        self._repo = repository
        self._entry = catalog.snapshot()  # Memento for cancel

        self.setWindowTitle("eter — Settings")
        self.setMinimumSize(820, 540)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(PackEditor(catalog, pack_service, manifest), "Stations")
        tabs.addTab(self._prefs_tab(), "Preferences")
        root.addWidget(tabs)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _prefs_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.notifications_cb = QCheckBox("Show a notification when the song changes")
        self.notifications_cb.setChecked(self._read_bool("notifications", True))
        lay.addWidget(self.notifications_cb)

        self.autostart_cb = QCheckBox("Launch eter at login")
        self.autostart_cb.setChecked(autostart.is_enabled())
        lay.addWidget(self.autostart_cb)

        self.updates_cb = QCheckBox("Check for updates on launch")
        self.updates_cb.setChecked(self._read_bool("check_updates", True))
        lay.addWidget(self.updates_cb)

        self.resume_cb = QCheckBox("Resume last station on launch")
        self.resume_cb.setChecked(self._read_bool("auto_resume", True))
        lay.addWidget(self.resume_cb)

        vol = QHBoxLayout()
        vol.addWidget(QLabel("Default volume"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(int(float(self._settings.value("volume", 0.8)) * 100))
        vol.addWidget(self.volume)
        lay.addLayout(vol)
        lay.addStretch(1)
        return w

    def _on_save(self) -> None:
        self._settings.setValue("notifications", self.notifications_cb.isChecked())
        self._settings.setValue("check_updates", self.updates_cb.isChecked())
        self._settings.setValue("auto_resume", self.resume_cb.isChecked())
        self._settings.setValue("volume", self.volume.value() / 100.0)
        autostart.set_enabled(self.autostart_cb.isChecked())
        self._repo.save(self._catalog)
        self.accept()

    def reject(self) -> None:  # noqa: D401 - also covers the window close button
        self._catalog.restore(self._entry)  # revert live catalog edits
        super().reject()

    def _read_bool(self, key: str, default: bool) -> bool:
        v = self._settings.value(key, default)
        if isinstance(v, str):
            return v.lower() in ("1", "true", "yes", "on")
        return bool(v)
