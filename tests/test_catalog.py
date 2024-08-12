from PySide6.QtMultimedia import QMediaPlayer

from eter import commands, urlprep
from eter.catalog import Catalog, Pack, Station
from eter.catalog_repository import CatalogRepository
from eter.menu_builder import TrayMenuBuilder
from eter.metadata import NowPlayingResolver
from eter.seeder import DefaultCatalogSeeder


# ---- Composite domain ----
def test_pack_groups_and_favorites():
    p = Pack("ex", "ex", stations=[
        Station("A", "http://a", "Serbia"),
        Station("B", "http://b", "Serbia"),
        Station("C", "http://c", "Croatia"),
    ])
    cat = Catalog([p], favorites={"http://a"})
    assert [g.name for g in p.groups()] == ["Serbia", "Croatia"]
    assert len(p.groups()[0].children()) == 2
    assert [s.name for s in cat.favorites_stations()] == ["A"]
    assert len(cat.all_stations()) == 3


def test_visible_packs():
    cat = Catalog([Pack("a", "A", visible=True), Pack("b", "B", visible=False)])
    assert [p.id for p in cat.visible_packs()] == ["a"]


# ---- Seeder (Factory) + Repository ----
def test_seeder_builds_default_packs():
    cat = DefaultCatalogSeeder().build()
    ids = [p.id for p in cat.packs()]
    assert ids == ["makedonski", "ex-yu", "world", "custom"]
    assert all(p.visible for p in cat.packs())


def test_repository_seeds_and_roundtrips(tmp_path):
    repo = CatalogRepository(tmp_path / "catalog.json")
    cat = repo.load()  # first run -> seeded + saved
    assert (tmp_path / "catalog.json").exists()
    url = cat.pack("world").stations[0].url
    cat.set_favorite(url, True)
    cat.set_visible("world", False)
    repo.save(cat)
    reloaded = repo.load()
    assert reloaded.is_favorite(url)
    assert reloaded.pack("world").visible is False


# ---- Memento ----
def test_memento_restore():
    cat = DefaultCatalogSeeder().build()
    snap = cat.snapshot()
    cat.remove_pack("world")
    assert cat.pack("world") is None
    cat.restore(snap)
    assert cat.pack("world") is not None


# ---- Commands + CommandStack (undo/redo) ----
def test_command_stack_undo_redo():
    cat = Catalog([Pack("custom", "Custom")])
    stack = commands.CommandStack()

    stack.do(commands.CreatePack(cat, "New"))
    assert len(cat.packs()) == 2
    stack.undo()
    assert len(cat.packs()) == 1
    stack.redo()
    assert len(cat.packs()) == 2

    pid = cat.packs()[-1].id
    stack.do(commands.SetVisible(cat, pid, False))
    assert cat.pack(pid).visible is False
    stack.undo()
    assert cat.pack(pid).visible is True


def test_move_station_command():
    cat = Catalog([
        Pack("a", "A", stations=[Station("X", "http://x")]),
        Pack("b", "B", stations=[]),
    ])
    stack = commands.CommandStack()
    stack.do(commands.MoveStation(cat, "a", 0, "b"))
    assert [s.name for s in cat.pack("a").stations] == []
    assert [s.name for s in cat.pack("b").stations] == ["X"]
    stack.undo()
    assert [s.name for s in cat.pack("a").stations] == ["X"]


# ---- URL prep chain ----
def test_urlprep_normalizes_shoutcast():
    assert urlprep.prepare("http://h:8020/;stream.nsv") == "http://h:8020/"
    assert not urlprep.needs_network("http://h:8020/;stream.nsv")
    assert urlprep.needs_network("http://h/listen.pls")


# ---- Menu builder shows visible packs only ----
def test_menu_builder_visible_only():
    from PySide6.QtGui import QActionGroup
    from PySide6.QtWidgets import QMenu

    cat = Catalog([
        Pack("a", "A", visible=True, stations=[Station("S1", "http://s1")]),
        Pack("b", "B", visible=False, stations=[Station("S2", "http://s2")]),
    ])
    menu = QMenu()
    builder = TrayMenuBuilder(cat, "", lambda s: None, lambda s: False)
    builder.build_into(menu, QActionGroup(menu))
    titles = [a.menu().title() for a in menu.actions() if a.menu()]
    assert titles == ["A"]
    assert [s.name for s, _ in builder.station_actions] == ["S1"]


# ---- Metadata resolver: authoritative outranks web (Strategy priority) ----
def test_resolver_authoritative_outranks_web():
    resolver = NowPlayingResolver(QMediaPlayer())
    seen = []
    resolver.titleChanged.connect(seen.append)
    resolver._on_web_title("Web Guess")
    assert seen[-1] == "Web Guess"
    resolver._on_authoritative("Real Title")
    assert seen[-1] == "Real Title"
    # web updates no longer override the authoritative title
    resolver._on_web_title("Another Guess")
    assert seen[-1] == "Real Title"
