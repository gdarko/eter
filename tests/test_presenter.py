from PySide6.QtWidgets import QApplication

from eter.app import TrayApp
from eter.catalog_repository import CatalogRepository
from eter.presenter import TrayPresenter, WindowPresenter


def _app(tmp_path):
    repo = CatalogRepository(tmp_path / "catalog.json")
    catalog = repo.load()  # seeded with the default packs
    return TrayApp(QApplication.instance(), catalog, repo)


def test_auto_uses_window_without_tray(tmp_path):
    # offscreen has no system tray, so Auto resolves to the window
    app = _app(tmp_path)
    assert isinstance(app._presenter, WindowPresenter)


def test_mode_window_forces_window(tmp_path, isolated_settings):
    isolated_settings.setValue("display_mode", "window")
    isolated_settings.sync()
    assert isinstance(_app(tmp_path)._presenter, WindowPresenter)


def test_mode_tray_without_tray_falls_back_to_window(tmp_path, isolated_settings):
    isolated_settings.setValue("display_mode", "tray")
    isolated_settings.sync()
    assert isinstance(_app(tmp_path)._presenter, WindowPresenter)


def test_window_panel_lists_and_plays(tmp_path):
    app = _app(tmp_path)
    panel = app._presenter.panel
    assert panel._station_items  # tree populated from the catalog
    st, item = panel._station_items[0]
    panel._on_item(item)
    assert app.current is st


def test_tray_presenter_builds_menu(tmp_path):
    app = _app(tmp_path)
    tp = TrayPresenter(app)
    tp.rebuild()
    assert tp._station_actions  # stations rendered as menu actions
    texts = [a.text() for a in tp.menu.actions()]
    assert any("Quit" in t for t in texts)
