import pytest
from PySide6.QtMultimedia import QMediaDevices

from eter.player import RadioPlayer


def test_player_monitors_default_output():
    p = RadioPlayer()
    # a device monitor is wired so playback can follow the system default output
    assert isinstance(p._devices, QMediaDevices)


def test_sync_default_output_is_safe():
    p = RadioPlayer()
    # invoking the handler must never raise, whatever devices the host has
    p._sync_default_output()
    p._sync_default_output()


def test_sync_switches_output_to_default():
    outs = QMediaDevices.audioOutputs()
    default = QMediaDevices.defaultAudioOutput()
    if len(outs) < 2 or default.isNull():
        pytest.skip("needs >=2 audio output devices")
    other = next(d for d in outs if d != default)
    p = RadioPlayer()
    p._audio.setDevice(other)  # pretend we're stuck on a stale device
    p._sync_default_output()
    assert p._audio.device() == default
