"""eter — a cross-platform menu-bar internet radio player."""

import re

# Single source of truth for the app version. pyproject, the PyInstaller spec,
# and the release workflow all derive from this. Use PEP 440 (e.g. "1.0.0rc1").
__version__ = "1.0.0rc6"


def display_version(version: str = __version__) -> str:
    """Render the version in SemVer style for the UI (1.0.0rc1 -> 1.0.0-rc.1)."""
    m = re.fullmatch(r"(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?", version)
    if not m:
        return version
    base, pre, num = m.groups()
    return f"{base}-{pre}.{num}" if pre else base
