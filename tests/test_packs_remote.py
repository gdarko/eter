from eter import commands, config, pack_service
from eter.catalog import Catalog, Pack, Station
from eter.pack_service import RemotePackService
from eter.seeder import DefaultCatalogSeeder


def _managed(stations):
    return Pack("world", "World", source_id="world", source_version=1, stations=stations)


def test_is_managed():
    assert Pack("w", "W", source_id="w").is_managed
    assert not Pack("c", "Custom").is_managed


def test_update_replaces_managed_pack_and_keeps_favorite():
    cat = Catalog([_managed([Station("A", "http://a")])])
    cat.set_favorite("http://a", True)  # star a curated station (overlay)
    stack = commands.CommandStack()
    remote = [Station("A2", "http://a"), Station("B", "http://b")]
    stack.do(commands.UpdatePack(cat, "world", "World v2", remote, 2))

    w = cat.pack("world")
    assert [s.name for s in w.stations] == ["A2", "B"]  # replaced wholesale
    assert w.name == "World v2" and w.source_version == 2
    assert cat.is_favorite("http://a")  # favourite survives by URL
    stack.undo()
    assert [s.name for s in cat.pack("world").stations] == ["A"]
    assert cat.pack("world").source_version == 1


def test_clone_pack_makes_editable_copy():
    cat = Catalog([_managed([Station("A", "http://a")])])
    stack = commands.CommandStack()
    stack.do(commands.ClonePack(cat, "world"))
    clone = next(p for p in cat.packs() if p.id != "world")
    assert clone.source_id is None and not clone.is_managed
    assert [s.name for s in clone.stations] == ["A"]
    assert clone.name.endswith("(copy)")
    stack.undo()
    assert len(cat.packs()) == 1


def test_toggle_favorite_command():
    cat = Catalog([_managed([Station("A", "http://a")])])
    stack = commands.CommandStack()
    stack.do(commands.ToggleFavorite(cat, "http://a"))
    assert cat.is_favorite("http://a")
    assert [s.name for s in cat.favorites_stations()] == ["A"]
    stack.undo()
    assert not cat.is_favorite("http://a")


def test_managed_pack_is_read_only():
    cat = Catalog([_managed([Station("A", "http://a")])])
    cat.set_pack_stations("world", [])      # ignored: curated pack
    cat.rename_pack("world", "X")           # ignored: curated pack
    assert len(cat.pack("world").stations) == 1
    assert cat.pack("world").name == "World"


def test_add_pack_command():
    cat = Catalog([Pack("custom", "My Stations")])
    stack = commands.CommandStack()
    stack.do(commands.AddPack(cat, "jazz", "Jazz", 1, [Station("X", "http://x")]))
    p = cat.pack("jazz")
    assert p is not None and p.is_managed and p.source_version == 1
    stack.undo()
    assert cat.pack("jazz") is None


def test_seeder_marks_managed_and_default_favorites():
    cat = DefaultCatalogSeeder().build()
    mk = cat.pack("makedonski")
    assert mk.is_managed and mk.source_id == "makedonski" and mk.source_version >= 1
    assert not cat.pack("custom").is_managed
    assert len(cat.favorites_stations()) >= 1  # presets ship a couple of stars


def test_config_manifest_and_version():
    assert [p["id"] for p in config.bundled_manifest()] == ["makedonski", "ex-yu", "world"]
    assert config.pack_version("makedonski") >= 1


def test_remote_pack_service_parses(monkeypatch):
    def fake(url, timeout=8.0):
        if url.endswith("index.json"):
            return {"packs": [{"id": "world", "name": "World", "version": 3}]}
        return {
            "id": "world", "name": "World", "version": 3,
            "stations": [{"name": "A", "url": "http://a"}],
        }

    monkeypatch.setattr(pack_service, "_fetch_json", fake)
    svc = RemotePackService(base_url="http://example/")

    manifest = []
    svc.manifestReady.connect(lambda m: manifest.extend(m))
    svc._check()
    assert manifest == [("world", "World", 3)]

    got = []
    svc.packReady.connect(lambda i, n, v, s: got.append((i, n, v, [x.name for x in s])))
    svc._fetch_pack("world")
    assert got == [("world", "World", 3, ["A"])]
