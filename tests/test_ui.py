from eter import icons, theme
from eter.widgets import MonogramBadge, NowPlayingHeader


def test_tray_icon_states_render():
    for active in (False, True):
        icon = icons.tray_icon(active)
        assert not icon.isNull()
        assert icon.availableSizes()


def test_glyph_pixmap():
    pm = icons.glyph_pixmap("play", "#ffffff", 40)
    assert pm.width() == 40 and not pm.isNull()


def test_monogram_deterministic():
    a, b = MonogramBadge(), MonogramBadge()
    a.set_station("Naxi Cafe")
    b.set_station("Naxi Cafe")
    assert a._color.name() == b._color.name()
    assert a._letter == "N"


def test_header_state_chip_and_volume():
    h = NowPlayingHeader(theme.DARK)
    h.set_station("Naxi Cafe")
    h.set_state("playing")
    assert h.chip.text() == "LIVE"
    h.set_state("stopped")
    assert h.chip.text() == "OFF"
    h.set_volume(42)
    assert h.pct.text() == "42%"
