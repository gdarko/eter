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


def test_window_close_quits_when_no_tray(tmp_path, monkeypatch):
    app = _app(tmp_path)  # offscreen -> no tray
    p = app._presenter
    assert p.tray is None
    quit_calls = []
    monkeypatch.setattr(app, "quit", lambda: quit_calls.append(True))
    assert p._on_window_close() is True  # allow the close
    assert quit_calls == [True] and p._closing is True


def test_window_close_hides_to_tray_when_present(tmp_path):
    app = _app(tmp_path)
    p = app._presenter
    p.tray = object()  # pretend a tray exists
    assert p._on_window_close() is False  # hide to tray, do not quit
    assert p._closing is False


def test_window_shutdown_hides_without_quitting(tmp_path):
    app = _app(tmp_path)
    p = app._presenter
    p.shutdown()
    assert p._closing is True and not p.window.isVisible()


def test_main_window_close_honours_callback():
    from eter.presenter import _MainWindow

    kept = _MainWindow(lambda: False)  # False -> stay alive (hidden)
    kept.show()
    kept.close()
    assert not kept.isVisible()  # ignored the close, hid instead

    closed = _MainWindow(lambda: True)  # True -> real close
    closed.show()
    closed.close()
    assert not closed.isVisible()


def test_tray_presenter_builds_menu(tmp_path):
    app = _app(tmp_path)
    tp = TrayPresenter(app)
    tp.rebuild()
    assert tp._station_actions  # stations rendered as menu actions
    texts = [a.text() for a in tp.menu.actions()]
    assert any("Quit" in t for t in texts)
