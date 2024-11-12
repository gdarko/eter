import array

from PySide6.QtMultimedia import QAudioFormat

from eter.player import _buffer_level, rms_from_bytes

F = QAudioFormat.SampleFormat


def test_rms_silence():
    raw = array.array("f", [0.0] * 1000).tobytes()
    assert rms_from_bytes(raw, F.Float) == 0.0


def test_rms_constant_float():
    raw = array.array("f", [0.5] * 1000).tobytes()
    assert abs(rms_from_bytes(raw, F.Float) - 0.5) < 1e-6


def test_rms_int16_fullscale():
    raw = array.array("h", [32767, -32768] * 500).tobytes()
    assert 0.99 < rms_from_bytes(raw, F.Int16) <= 1.0


def test_rms_empty():
    assert rms_from_bytes(b"", F.Float) == 0.0


def test_rms_unknown_format():
    assert rms_from_bytes(b"\x00\x01\x02\x03", F.Unknown) == 0.0
