"""Group the catalog and every installed game into the TUI's home-screen shelf."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from omamods.filesystem import ReadableFiles
from omamods.heroic_games import list_heroic_games
from omamods.installed_games import InstalledGame, InstalledScan, combine_scans
from omamods.manifests import GameManifest
from omamods.steam_installed import list_steam_games
from omamods.steam_libraries import discover_libraries

MOD_READY = "mod-ready"
CATALOG = "catalog"
LIBRARY = "library"
SHELF_SECTIONS: tuple[str, ...] = (MOD_READY, CATALOG, LIBRARY)


@dataclass(frozen=True)
class ShelfEntry:
    """One game row: a catalog game, an installed game, or both."""

    key: str
    name: str
    section: str
    installs: tuple[InstalledGame, ...]
    manifest: GameManifest | None = None

    @property
    def install(self) -> InstalledGame | None:
        """Prefer a complete install; e.g. ``entry.install.install_path``."""
        ready = [game for game in self.installs if game.ready]
        return (ready or list(self.installs) or [None])[0]


@dataclass(frozen=True)
class GameShelf:
    """Everything the home screen lists, plus where it looked."""

    entries: tuple[ShelfEntry, ...]
    libraries: tuple[Path, ...]
    warnings: tuple[str, ...]

    def section(self, name: str) -> tuple[ShelfEntry, ...]:
        """Filter by section; for example, ``shelf.section(MOD_READY)``."""
        return tuple(entry for entry in self.entries if entry.section == name)


ShelfScanner = Callable[[], GameShelf]


def _catalog_entry(
    manifest: GameManifest, games: tuple[InstalledGame, ...], mod_ready: frozenset[str]
) -> ShelfEntry:
    # Match Steam IDs, never titles: titles differ by edition and trademark signs.
    app_id = str(manifest.steam_app_id) if manifest.steam_app_id else None
    installs = tuple(g for g in games if g.store == "Steam" and g.app_id == app_id)
    section = MOD_READY if manifest.id in mod_ready else CATALOG
    return ShelfEntry(manifest.id, manifest.name, section, installs, manifest)


def _library_entry(game: InstalledGame) -> ShelfEntry:
    key = f"{game.store.lower()}:{game.app_id}"
    return ShelfEntry(key, game.name, LIBRARY, (game,))


def _shelf_order(entry: ShelfEntry) -> tuple[int, bool, str]:
    return (
        SHELF_SECTIONS.index(entry.section),
        entry.install is None,
        entry.name.casefold(),
    )


def build_shelf(
    catalog: tuple[GameManifest, ...],
    mod_ready: frozenset[str],
    found: InstalledScan,
    libraries: tuple[Path, ...],
) -> GameShelf:
    """Sort games into sections; e.g. ``build_shelf(catalog, {'cronos'}, scan, libs)``."""
    entries = [_catalog_entry(item, found.games, mod_ready) for item in catalog]
    claimed = {(g.store, g.app_id) for entry in entries for g in entry.installs}
    entries.extend(
        _library_entry(game)
        for game in found.games
        if (game.store, game.app_id) not in claimed
    )
    ordered = tuple(sorted(entries, key=_shelf_order))
    return GameShelf(ordered, libraries, found.warnings)


@dataclass(frozen=True)
class ShelfSources:
    """Where to look for games; injected so tests can use fake files."""

    catalog: Callable[[], tuple[GameManifest, ...]]
    steam_roots: tuple[Path, ...]
    heroic_roots: tuple[Path, ...]
    files: ReadableFiles
    mod_ready: frozenset[str]


def scan_shelf(sources: ShelfSources) -> GameShelf:
    """Look in Steam and Heroic; for example, ``scan_shelf(sources)``."""
    files = sources.files
    libraries = discover_libraries(sources.steam_roots, files)
    steam = list_steam_games(libraries, files)
    heroic = list_heroic_games(sources.heroic_roots, files)
    found = combine_scans(InstalledScan((), libraries.warnings), steam, heroic)
    return build_shelf(sources.catalog(), sources.mod_ready, found, libraries.libraries)
