"""Best-effort 'launch at login' across macOS, Windows, and Linux.

All operations are wrapped so a failure never breaks the app; callers should
treat is_enabled() as the source of truth after set_enabled().
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_ID = "eter"
_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> list[str]:
    if getattr(sys, "frozen", False):  # packaged (PyInstaller) build
        return [sys.executable]
    return [sys.executable, "-m", "eter"]


# ---- Linux (XDG autostart) ----
def _linux_path() -> Path:
    return Path.home() / ".config" / "autostart" / f"{APP_ID}.desktop"


def _linux_enable() -> None:
    p = _linux_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "[Desktop Entry]\nType=Application\nName=eter\n"
        f"Exec={' '.join(_launch_command())}\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )


# ---- macOS (LaunchAgent) ----
def _mac_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "app.eter.plist"


def _mac_enable() -> None:
    args = "".join(f"    <string>{a}</string>\n" for a in _launch_command())
    p = _mac_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        "  <key>Label</key><string>app.eter</string>\n"
        "  <key>ProgramArguments</key><array>\n" + args + "  </array>\n"
        "  <key>RunAtLoad</key><true/>\n"
        "</dict></plist>\n",
        encoding="utf-8",
    )


# ---- Windows (HKCU Run key) ----
def _win_command() -> str:
    return " ".join(f'"{a}"' if " " in a else a for a in _launch_command())


def _win_enable() -> None:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, _win_command())


def _win_disable() -> None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_ID)
    except FileNotFoundError:
        pass


def _win_is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_ID)
            return True
    except FileNotFoundError:
        return False


# ---- public API ----
def is_enabled() -> bool:
    try:
        if sys.platform == "darwin":
            return _mac_path().exists()
        if sys.platform.startswith("win"):
            return _win_is_enabled()
        return _linux_path().exists()
    except Exception:  # noqa: BLE001
        return False


def set_enabled(enabled: bool) -> bool:
    """Enable/disable autostart; returns the actual resulting state."""
    try:
        if sys.platform == "darwin":
            _mac_enable() if enabled else _mac_path().unlink(missing_ok=True)
        elif sys.platform.startswith("win"):
            _win_enable() if enabled else _win_disable()
        else:
            _linux_enable() if enabled else _linux_path().unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return is_enabled()
