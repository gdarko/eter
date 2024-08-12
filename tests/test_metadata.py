from eter.metadata import parse_stream_title


def test_parses_streamtitle():
    block = b"StreamTitle='Artist - Song';StreamUrl='';\x00\x00\x00"
    assert parse_stream_title(block) == "Artist - Song"


def test_empty_title():
    block = b"StreamTitle='';\x00"
    assert parse_stream_title(block) == ""


def test_no_marker():
    assert parse_stream_title(b"\x00\x00") is None


def test_utf8_title():
    block = "StreamTitle='Ð‡Ð°Ñ€ — песна';".encode("utf-8") + b"\x00"
    assert parse_stream_title(block) == "Ð‡Ð°Ñ€ — песна"
