from eter import __version__, display_version


def test_semver_rendering():
    assert display_version("1.0.0rc1") == "1.0.0-rc.1"
    assert display_version("0.2.0rc3") == "0.2.0-rc.3"
    assert display_version("1.0.0b2") == "1.0.0-b.2"
    assert display_version("1.2.3") == "1.2.3"


def test_unparseable_passthrough():
    assert display_version("weird") == "weird"


def test_shipped_version_renders():
    assert display_version(__version__)  # never empty / never raises
