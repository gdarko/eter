from PySide6.QtWidgets import QMenu, QWidgetAction

from eter import tray_menu
from eter.tray_menu import NativeTrayMenu, PopupTrayMenu, make_tray_menu


class _StubApp:
    """Minimal stand-in exposing only what the strategies touch."""

    def __init__(self, state="stopped", current=None, volume=0.7):
        self.state = state
        self.current = current
        self._volume = volume
        self.header_action = QWidgetAction(None)
        self.toggled = False

    def _np_text(self):
        return "No station selected" if self.current is None else "Naxi — song"

    def _toggle_play(self):
        self.toggled = True

    def _on_volume(self, v):
        self._volume = v / 100


def _build_native(app):
    """Build a native menu, returning the (strategy, menu) — both kept alive."""
    menu = QMenu()
    strat = NativeTrayMenu(app)
    strat.build_now_playing(menu)
    return strat, menu


def test_native_menu_has_now_playing_toggle_and_volume():
    strat, menu = _build_native(_StubApp())
    assert strat._now.text() == "No station selected" and not strat._now.isEnabled()
    assert strat._toggle in menu.actions()
    vol_labels = [act.text() for _lvl, act in strat._vol_actions]
    assert "Mute" in vol_labels and "50%" in vol_labels


def test_native_toggle_label_and_enabled_track_state():
    strat, _menu = _build_native(_StubApp(state="playing", current=object()))
    assert strat._toggle.text() == "Stop" and strat._toggle.isEnabled()
    strat.app.state = "stopped"
    strat.app.current = None
    strat.refresh()
    assert strat._toggle.text() == "Play" and not strat._toggle.isEnabled()


def test_native_toggle_click_calls_app():
    strat, _menu = _build_native(_StubApp(state="playing", current=object()))
    strat._toggle.trigger()
    assert strat.app.toggled is True


def test_native_volume_click_sets_volume():
    app = _StubApp(volume=0.7)
    strat, _menu = _build_native(app)
    act = next(a for _lvl, a in strat._vol_actions if a.text() == "50%")
    act.trigger()
    assert abs(app._volume - 0.5) < 1e-9


def test_native_volume_checkmark_is_closest_step():
    strat, _menu = _build_native(_StubApp(volume=0.72))  # nearest step = 75
    checked = [lvl for lvl, act in strat._vol_actions if act.isChecked()]
    assert checked == [75]


def test_popup_menu_adds_header_widget():
    app = _StubApp()
    menu = QMenu()
    PopupTrayMenu(app).build_now_playing(menu)
    assert app.header_action in menu.actions()


def test_factory_selects_strategy_by_platform(monkeypatch):
    monkeypatch.setattr(tray_menu.sys, "platform", "linux")
    assert isinstance(make_tray_menu(_StubApp()), NativeTrayMenu)
    for other in ("darwin", "win32"):
        monkeypatch.setattr(tray_menu.sys, "platform", other)
        assert isinstance(make_tray_menu(_StubApp()), PopupTrayMenu)
