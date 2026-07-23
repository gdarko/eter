from PySide6.QtWidgets import QApplication

from eter.app import TrayApp
from eter.catalog_repository import CatalogRepository


def _tray(tmp_path):
    repo = CatalogRepository(tmp_path / "catalog.json")
    catalog = repo.load()  # seeded with the default packs
    return TrayApp(QApplication.instance(), catalog, repo), catalog


def _sleep_actions(tray):
    """The active presenter's sleep-timer actions (tray menu or window button)."""
    p = tray._presenter
    return p.panel._sleep_actions if hasattr(p, "panel") else p._sleep_actions


def test_sleep_timer_set_and_clear(tmp_path):
    tray, _ = _tray(tmp_path)
    tray._set_sleep(30)
    assert tray._sleep_minutes == 30
    assert tray._sleep_timer.isActive()
    assert [m for m, a in _sleep_actions(tray) if a.isChecked()] == [30]
    tray._set_sleep(0)
    assert not tray._sleep_timer.isActive()


def test_sleep_fired_stops_playback(tmp_path):
    tray, catalog = _tray(tmp_path)
    tray.current = catalog.all_stations()[0]
    tray.state = "playing"
    tray._sleep_minutes = 15
    tray._on_sleep_fired()
    assert tray._sleep_minutes == 0
    assert tray.state == "stopped"


def test_auto_resume_on(tmp_path, isolated_settings):
    repo = CatalogRepository(tmp_path / "catalog.json")
    catalog = repo.load()
    st = catalog.all_stations()[0]
    isolated_settings.setValue("auto_resume", True)
    isolated_settings.setValue("last_station", st.key())
    isolated_settings.sync()
    tray = TrayApp(QApplication.instance(), catalog, repo)
    assert tray.current is not None and tray.current.key() == st.key()
    tray.player.stop()


def test_auto_resume_off(tmp_path, isolated_settings):
    repo = CatalogRepository(tmp_path / "catalog.json")
    catalog = repo.load()
    st = catalog.all_stations()[0]
    isolated_settings.setValue("auto_resume", False)
    isolated_settings.setValue("last_station", st.key())
    isolated_settings.sync()
    tray = TrayApp(QApplication.instance(), catalog, repo)
    assert tray.current is not None and tray.current.key() == st.key()
    assert tray.state == "stopped"
