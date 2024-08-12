from eter.nowplaying_web import _combine, _extract_fields, extract_by_class

# A decoy "recently played" slider precedes the real current-song container.
SAMPLE = """
<div class="songs-slider">
  <div class="item"><h3 class="artist">DECOY ARTIST</h3><h3 class="song">DECOY SONG</h3></div>
</div>
<div class="lyrics-wrapper-inner">
  <div class="song-info">
    <span class="close"><svg><use xlink:href="#x"></use></svg></span>
    <h2 class="artist">Fun Feat Janelle Monae</h2>
    <h2 class="song">Rock &amp; Roll</h2>
  </div>
</div>
"""


def test_scoped_extraction_prefers_container():
    got = _extract_fields(SAMPLE, "song-info", {"artist": "artist", "song": "song"})
    assert got["artist"] == "Fun Feat Janelle Monae"
    assert got["song"] == "Rock & Roll"  # entity unescaped


def test_unscoped_grabs_first_match():
    assert extract_by_class(SAMPLE, "artist") == "DECOY ARTIST"


def test_missing_container_yields_nothing():
    assert _extract_fields(SAMPLE, "no-such-class", {"artist": "artist"}) == {}


def test_combine():
    assert _combine({}, "A", "B") == "A - B"
    assert _combine({"format": "{artist} — {song}"}, "A", "B") == "A — B"
    assert _combine({}, "", "B") == "B"
    assert _combine({}, "A", "") == "A"
    assert _combine({}, None, None) is None
