"""Tray + UI icons, drawn from embedded SVG (crisp, no binary assets).

The tray icon is a tabletop radio: an outline when idle, filled speaker + eq
bars when playing. On macOS it is returned as a template/mask so it adapts to
the light/dark menu bar; elsewhere it is tinted.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_IS_MAC = sys.platform == "darwin"
ACCENT = "#E8543F"
_IDLE = "#9AA0A6"

# --- tray: tabletop radio (viewBox 0 0 100 100) ---------------------------
_RADIO_IDLE = """
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>
  <g fill='none' stroke='@C@' stroke-width='7' stroke-linecap='round' stroke-linejoin='round'>
    <line x1='70' y1='36' x2='90' y2='11'/>
    <circle cx='90' cy='11' r='3.5' fill='@C@' stroke='none'/>
    <rect x='11' y='34' width='78' height='53' rx='11'/>
    <circle cx='35' cy='61' r='13'/>
    <circle cx='35' cy='61' r='2.5' fill='@C@' stroke='none'/>
    <circle cx='69' cy='49' r='5'/>
    <line x1='56' y1='64' x2='81' y2='64' stroke-width='5.5'/>
    <line x1='56' y1='74' x2='81' y2='74' stroke-width='5.5'/>
  </g>
</svg>
"""

_RADIO_PLAY = """
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>
  <g stroke='@C@' stroke-width='7' stroke-linecap='round' stroke-linejoin='round'>
    <line x1='70' y1='36' x2='90' y2='11' fill='none'/>
    <circle cx='90' cy='11' r='3.5' fill='@C@' stroke='none'/>
    <rect x='11' y='34' width='78' height='53' rx='11' fill='none'/>
    <circle cx='35' cy='61' r='13' fill='@C@' stroke='none'/>
    <g fill='@C@' stroke='none'>
      <rect x='55' y='65' width='6' height='13' rx='3'/>
      <rect x='63.5' y='57' width='6' height='21' rx='3'/>
      <rect x='72' y='61' width='6' height='17' rx='3'/>
      <rect x='80.5' y='53' width='6' height='25' rx='3'/>
    </g>
  </g>
</svg>
"""

# --- small UI glyphs ------------------------------------------------------
_GLYPH = {
    "play": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
    "<path d='M8 5.5 L18 12 L8 18.5 Z' fill='@C@'/></svg>",
    "stop": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
    "<rect x='6.5' y='6.5' width='11' height='11' rx='2.5' fill='@C@'/></svg>",
    "speaker": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
    "<g fill='@C@'><path d='M4 9 H7 L11 5 V19 L7 15 H4 Z'/></g>"
    "<g fill='none' stroke='@C@' stroke-width='1.8' stroke-linecap='round'>"
    "<path d='M14 9 Q16.5 12 14 15'/><path d='M16.5 7 Q20.5 12 16.5 17'/></g></svg>",
}


def _render(svg: str, color: str, px: int) -> QPixmap:
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.replace("@C@", color).encode("utf-8")))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pm


def tray_icon(active: bool) -> QIcon:
    svg = _RADIO_PLAY if active else _RADIO_IDLE
    color = "#000000" if _IS_MAC else (ACCENT if active else _IDLE)
    icon = QIcon()
    for px in (18, 22, 36, 44, 54, 66, 88):
        icon.addPixmap(_render(svg, color, px))
    if _IS_MAC:
        icon.setIsMask(True)
    return icon


def glyph_icon(kind: str, color: str, px: int = 40) -> QIcon:
    """A small monochrome UI glyph (play/stop/speaker) in the given color."""
    return QIcon(_render(_GLYPH[kind], color, px))


def glyph_pixmap(kind: str, color: str, px: int) -> QPixmap:
    return _render(_GLYPH[kind], color, px)
