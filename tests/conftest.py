import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Redirect eter preferences to a throwaway ini per test (no real config,
    no network from the update check)."""
    from eter import config

    path = str(tmp_path / "prefs.ini")
    monkeypatch.setattr(
        config, "settings", lambda: QSettings(path, QSettings.Format.IniFormat)
    )
    s = config.settings()
    s.setValue("check_updates", False)
    s.setValue("check_pack_updates", False)
    s.sync()
    return s
