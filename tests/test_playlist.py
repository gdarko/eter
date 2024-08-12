from eter import playlist


def test_looks_like_playlist():
    assert playlist.looks_like_playlist("http://x/listen.pls")
    assert playlist.looks_like_playlist("http://x/stream.m3u")
    assert playlist.looks_like_playlist("http://x/stream.m3u8")
    assert not playlist.looks_like_playlist("http://x:8000/;stream.nsv")
    assert not playlist.looks_like_playlist("https://x/live64")


def test_parse_pls():
    text = "[playlist]\nNumberOfEntries=1\nFile1=http://host:8000/stream\nTitle1=X\n"
    assert playlist._parse_pls(text) == "http://host:8000/stream"


def test_parse_pls_none():
    assert playlist._parse_pls("[playlist]\nNumberOfEntries=0\n") is None


def test_parse_m3u_skips_comments():
    text = "#EXTM3U\n#EXTINF:-1,Radio\nhttp://host:8000/stream\n"
    assert playlist._parse_m3u(text) == "http://host:8000/stream"


def test_normalize_strips_nsv_trick():
    assert (
        playlist.normalize_stream_url("http://h.example:8020/;stream.nsv")
        == "http://h.example:8020/"
    )
    assert (
        playlist.normalize_stream_url("https://h.example:9152/;stream.nsv")
        == "https://h.example:9152/"
    )


def test_normalize_leaves_working_urls_untouched():
    keep = [
        "http://176.9.117.123:9998/;",           # bare ;-trick, no extension
        "https://radiofortuna.ipradio.mk/;*.mp3",  # .mp3 probes fine
        "https://radiocnd.mms.mk/proxy/offnet/stream",
        "https://antenna5stream.neotel.mk/live64",
        "https://eu11.fastcast4u.com/starmain",
    ]
    for url in keep:
        assert playlist.normalize_stream_url(url) == url
