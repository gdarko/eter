"""Custom widgets for the now-playing header: monogram badge and header card."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .theme import Palette

_BADGE_COLORS = [
    "#E8543F", "#E39A3B", "#3FA796", "#4C86E8",
    "#8A5CF6", "#D65A9A", "#2FB673", "#5B6B7B",
]

_CHIP = {
    "playing": "LIVE",
    "buffering": "BUFFERING",
    "connecting": "CONNECTING",
    "reconnecting": "RECONNECTING",
    "stopped": "OFF",
    "error": "ERROR",
}
_ACTIVE = ("connecting", "buffering", "playing", "reconnecting")


class MonogramBadge(QWidget):
    """Circular badge showing a station's initial on a name-derived color."""

    def __init__(self, diameter: int = 44, parent=None):
        super().__init__(parent)
        self._d = diameter
        self.setFixedSize(diameter, diameter)
        self._letter = "•"
        self._color = QColor("#888")

    def set_station(self, name: str) -> None:
        name = (name or "").strip()
        self._letter = name[0].upper() if name else "•"
        self._color = QColor(
            _BADGE_COLORS[sum(map(ord, name)) % len(_BADGE_COLORS)] if name else "#888"
        )
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(0, 0, self._d, self._d)
        p.setPen(QColor("#ffffff"))
        f = self.font()
        f.setPixelSize(int(self._d * 0.44))
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._letter)


class NowPlayingHeader(QWidget):
    """The fixed-width now-playing card at the top of the menu."""

    playToggled = Signal()
    volumeChanged = Signal(int)

    def __init__(self, palette: Palette, width: int = 350, parent=None):
        super().__init__(parent)
        self._pal = palette
        self.setObjectName("npHeader")
        self.setFixedWidth(width)
        self._state = "stopped"
        self._station = ""
        self._title = ""
        self._song_full = ""
        self._build()
        self.apply_palette(palette)

    # ---- construction ----
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(11)

        top = QHBoxLayout()
        top.setSpacing(11)
        self.badge = MonogramBadge(44)
        top.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(3)
        namerow = QHBoxLayout()
        namerow.setSpacing(8)
        self.nameLbl = QLabel("No station")
        self.nameLbl.setObjectName("npName")
        self.chip = QLabel("OFF")
        self.chip.setObjectName("npChip")
        self.chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        namerow.addWidget(self.nameLbl, 0)
        namerow.addWidget(self.chip, 0)
        namerow.addStretch(1)
        info.addLayout(namerow)
        self.songLbl = QLabel("Pick a station below")
        self.songLbl.setObjectName("npSong")
        info.addWidget(self.songLbl)
        top.addLayout(info, 1)
        outer.addLayout(top)

        trans = QHBoxLayout()
        trans.setSpacing(10)
        self.playBtn = QToolButton()
        self.playBtn.setObjectName("npPlay")
        self.playBtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playBtn.setFixedSize(38, 38)
        self.playBtn.setIconSize(QSize(20, 20))
        self.playBtn.clicked.connect(self.playToggled)
        trans.addWidget(self.playBtn)
        self.spk = QLabel()
        self.spk.setObjectName("npSpk")
        trans.addWidget(self.spk)
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setObjectName("npVol")
        self.vol.setRange(0, 100)
        self.vol.valueChanged.connect(self._on_vol)
        trans.addWidget(self.vol, 1)
        self.pct = QLabel("70%")
        self.pct.setObjectName("npPct")
        self.pct.setFixedWidth(38)
        self.pct.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        trans.addWidget(self.pct)
        outer.addLayout(trans)

    # ---- public API ----
    def set_volume(self, v: int) -> None:
        self.vol.blockSignals(True)
        self.vol.setValue(v)
        self.vol.blockSignals(False)
        self.pct.setText(f"{v}%")

    def set_station(self, name: str) -> None:
        self._station = name or ""
        self.badge.set_station(name)
        self._refresh()

    def set_title(self, title: str) -> None:
        self._title = title or ""
        self._refresh()

    def set_state(self, state: str) -> None:
        self._state = state
        active = state in _ACTIVE
        self.playBtn.setIcon(icons.glyph_icon("stop" if active else "play", "#ffffff", 40))
        self._refresh()

    def apply_palette(self, p: Palette) -> None:
        self._pal = p
        self.spk.setPixmap(icons.glyph_pixmap("speaker", p.text2, 20))
        self.setStyleSheet(self._qss(p))
        self.playBtn.setIcon(
            icons.glyph_icon(
                "stop" if self._state in ("connecting", "buffering", "playing") else "play",
                "#ffffff",
                40,
            )
        )
        self._style_chip()

    # ---- internals ----
    def _on_vol(self, v: int) -> None:
        self.pct.setText(f"{v}%")
        self.volumeChanged.emit(v)

    def _refresh(self) -> None:
        self.nameLbl.setText(self._station or "No station")
        self.chip.setText(_CHIP.get(self._state, "OFF"))
        if self._state == "reconnecting":
            self._song_full = "Reconnecting…"
        elif self._title:
            self._song_full = self._title
        elif not self._station:
            self._song_full = "Pick a station below"
        elif self._state in ("stopped", "error"):
            self._song_full = "Stopped"
        elif self._state in ("connecting", "buffering"):
            self._song_full = "Tuning in…"
        else:
            self._song_full = "On air"
        self._apply_elide()
        self._style_chip()

    def _apply_elide(self) -> None:
        avail = max(40, self.songLbl.width() or (self.width() - 84))
        fm = QFontMetrics(self.songLbl.font())
        self.songLbl.setText(
            fm.elidedText(self._song_full, Qt.TextElideMode.ElideRight, avail)
        )

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._apply_elide()

    def _style_chip(self) -> None:
        p = self._pal
        if self._state == "playing":
            bg = QColor(p.accent)
            bg.setAlpha(38)
            self.chip.setStyleSheet(
                f"#npChip{{color:{p.accent};background:rgba({bg.red()},{bg.green()},"
                f"{bg.blue()},0.15);border-radius:6px;padding:1px 7px;"
                f"font-size:10px;font-weight:700;}}"
            )
        else:
            self.chip.setStyleSheet(
                f"#npChip{{color:{p.text2};background:{p.slot};border-radius:6px;"
                f"padding:1px 7px;font-size:10px;font-weight:700;}}"
            )

    def _qss(self, p: Palette) -> str:
        return f"""
        #npHeader {{ background: {p.surface}; border-radius: 12px; }}
        #npName {{ color: {p.text}; font-size: 14px; font-weight: 700; }}
        #npSong {{ color: {p.text2}; font-size: 12px; }}
        #npPlay {{ background: {p.accent}; border: none; border-radius: 19px; }}
        #npPlay:hover {{ background: {p.accent}; }}
        #npPlay:pressed {{ background: {p.accent}; }}
        #npPct {{ color: {p.text2}; font-size: 11px; }}
        #npVol::groove:horizontal {{ height: 4px; background: {p.slot};
            border-radius: 2px; }}
        #npVol::sub-page:horizontal {{ height: 4px; background: {p.accent};
            border-radius: 2px; }}
        #npVol::handle:horizontal {{ width: 14px; height: 14px; margin: -6px 0;
            border-radius: 7px; background: {p.accent}; }}
        """
