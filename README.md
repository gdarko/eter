# eter

A tiny cross-platform menu-bar internet radio player, built with Python and
PySide6 (Qt 6). Ships with curated starter packs, shows the current song, and
lets you add your own stations.

## Features

- Lives in the macOS menu bar, Windows tray, or Linux system tray.
- Lives in the menu bar / system tray on macOS, Windows, and Linux.
- Organize stations into your own editable packs, managed in Settings.
- Polished now-playing dropdown with a monogram badge and live status.
- Shows the current song, with optional notifications.
- Plays MP3 and AAC internet radio.
- Auto-reconnect, sleep timer, and resume on launch.
- Built-in update check. Light and dark aware.

## Run from source

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m eter
```

Click the tray icon, pick a station, and it plays. Use Settings to manage
stations and preferences.

## Configuration

The catalog lives in an editable JSON file (normally managed in Settings):

| OS      | Path |
|---------|------|
| macOS   | `~/Library/Preferences/eter/catalog.json` |
| Linux   | `~/.config/eter/catalog.json` |
| Windows | `%APPDATA%\eter\catalog.json` |

It is pack-centric: `{ "version": 4, "favorites": [urls], "packs": [ { "id",
"name", "visible", "source_id", "source_version", "stations": [ { "name", "url",
"group", "now_playing?" } ] } ] }`. Favourites are an overlay of station URLs, so
starring a curated station is not a content edit. A pack with a `source_id` is a
curated (read-only) pack; user packs have none. The bundled seed packs live in
`eter/resources/presets/*.json`.

## Updating packs

Curated packs are read-only mirrors of `eter/resources/presets/` (bundled with the
app and served raw from GitHub `main`). To publish a fix or a whole new pack between
releases: edit or add the pack JSON, bump its `version` there and in `index.json`,
and push to `main`. Apps pick it up in Settings via a per-pack **Update** (which
replaces the pack) and an **Available packs** list, without a new release. To
customize a curated pack, **Clone** it into your own editable pack; favourites
(an overlay) and visibility are kept across updates. `ETER_PACKS_URL` overrides the
source.

## Design

Clean layers (domain / persistence / app / UI). The catalog is a small tree
(`catalog.py`); persistence and undo snapshots are in `catalog_repository.py`;
editor edits are commands with undo/redo (`commands.py`); the tray menu is
assembled by `menu_builder.py`; playback is a thin facade over Qt Multimedia
(`player.py`); "now playing" is resolved from interchangeable sources
(`metadata_sources.py`). Each module notes the pattern it uses in a short
docstring line.

## Build and release

```bash
pyinstaller eter.spec        # dist/eter.app (mac), dist/eter/ (win, linux)
```

The spec bundles the Qt FFmpeg audio plugin and excludes unused Qt modules,
keeping the macOS app around 120 MB (about 50 MB compressed). Push a `v*` tag to
run `.github/workflows/release.yml`, which builds and publishes a macOS `.dmg`, a
Windows installer (`eter-Setup.exe`) plus portable `.zip`, and Linux `.tar.gz` /
`.deb` / `.rpm` to a GitHub Release. Builds are unsigned for now.

Set `ETER_GITHUB_REPO` (default `gdarko/eter` in `eter/updater.py`) to your repo
for the update checker. On stock GNOME the tray needs the AppIndicator extension.

## Tests

```bash
QT_QPA_PLATFORM=offscreen pytest
```

## License

MIT
