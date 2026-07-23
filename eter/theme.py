"""Light/dark palette and QSS for the styled popup."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

ACCENT = "#E8543F"
MENU_WIDTH = 350


@dataclass(frozen=True)
class Palette:
    bg: str          # menu background
    surface: str     # header card background
    text: str
    text2: str       # secondary text
    hover: str
    sep: str
    slot: str        # slider groove / inert track
    accent: str = ACCENT


DARK = Palette(
    bg="#202124", surface="#2a2b2f", text="#f1f3f5", text2="#9aa0a6",
    hover="#34363b", sep="#35363b", slot="#3c3e44",
)
LIGHT = Palette(
    bg="#ffffff", surface="#f5f6f8", text="#1c1d1f", text2="#6b7075",
    hover="#eceef1", sep="#e4e6e9", slot="#dfe1e5",
)


def current() -> Palette:
    """Pick a palette from the OS color scheme, falling back to bg luminance."""
    try:
        scheme = QApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return DARK
        if scheme == Qt.ColorScheme.Light:
            return LIGHT
    except Exception:  # noqa: BLE001 - older Qt / no app
        pass
    try:
        c = QApplication.palette().window().color()
        return DARK if (c.red() + c.green() + c.blue()) / 3 < 128 else LIGHT
    except Exception:  # noqa: BLE001
        return LIGHT


def menu_qss(p: Palette) -> str:
    return f"""
    QMenu {{
        background: {p.bg};
        border: 1px solid {p.sep};
        border-radius: 12px;
        padding: 6px;
    }}
    QMenu::item {{
        color: {p.text};
        padding: 8px 16px;
        margin: 1px 4px;
        border-radius: 8px;
    }}
    QMenu::item:selected {{ background: {p.hover}; }}
    QMenu::item:disabled {{ color: {p.text2}; }}
    QMenu::separator {{ height: 1px; background: {p.sep}; margin: 6px 12px; }}
    QMenu::right-arrow {{ width: 10px; height: 10px; }}
    """


def panel_qss(p: Palette) -> str:
    """QSS for the windowed player (mirrors the menu look for a normal window)."""
    return f"""
    QWidget#panel {{ background: {p.bg}; }}
    QTreeWidget#stations {{
        background: {p.bg};
        color: {p.text};
        border: none;
        outline: 0;
    }}
    QTreeWidget#stations::item {{ padding: 5px 4px; border-radius: 6px; }}
    QTreeWidget#stations::item:hover {{ background: {p.hover}; }}
    QTreeWidget#stations::item:selected {{ background: {p.accent}; color: #ffffff; }}
    QLabel#panelStatus {{ color: {p.text2}; font-size: 11px; }}
    QToolButton#panelBtn {{
        color: {p.text};
        background: {p.surface};
        border: none;
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QToolButton#panelBtn:hover {{ background: {p.hover}; }}
    QToolButton#panelBtn::menu-indicator {{ image: none; }}
    """
