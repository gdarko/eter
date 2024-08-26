"""Render a PNG app icon from the in-code SVG (used by Linux packaging)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from eter import icons  # noqa: E402


def main() -> None:
    out = sys.argv[1]
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    QApplication([])
    pm = icons._render(icons._RADIO_PLAY, icons.ACCENT, size)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if not pm.save(out):
        sys.exit(f"failed to write {out}")
    print("wrote", out)


if __name__ == "__main__":
    main()
