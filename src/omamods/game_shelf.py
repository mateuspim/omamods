"""Group the catalog and every installed game into the TUI's home-screen shelf."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from omamods.installed_games import InstalledGame, InstalledScan
from omamods.manifests import GameManifest
from omamods.nexus_config import UserSettings
from omamods.pak_games import PakGameCatalog, PakOverlayGame
from omamods.unreal_layout import UnrealLayout

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
    pak_game: PakOverlayGame | None = None
    unreal: UnrealLayout | None = None

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


ShelfScanner = Callable[[UserSettings], GameShelf]


def _catalog_entry(
    manifest: GameManifest, games: tuple[InstalledGame, ...], pak_games: PakGameCatalog
) -> ShelfEntry:
    # Match Steam IDs, never titles: titles differ by edition and trademark signs.
    app_id = str(manifest.steam_app_id) if manifest.steam_app_id else None
    installs = tuple(g for g in games if g.store == "Steam" and g.app_id == app_id)
    pak_game = pak_games.games.get(manifest.id)
    section = MOD_READY if pak_game else CATALOG
    return ShelfEntry(manifest.id, manifest.name, section, installs, manifest, pak_game)


def _library_entry(game: InstalledGame) -> ShelfEntry:
    key = f"{game.store.lower()}:{game.app_id}"
    return ShelfEntry(key, game.name, LIBRARY, (game,))


def shelf_order(entry: ShelfEntry) -> tuple[int, bool, str]:
    return (
        SHELF_SECTIONS.index(entry.section),
        entry.install is None,
        entry.name.casefold(),
    )


def build_shelf(
    catalog: tuple[GameManifest, ...],
    pak_games: PakGameCatalog,
    found: InstalledScan,
    libraries: tuple[Path, ...],
) -> GameShelf:
    """Sort games into sections; e.g. ``build_shelf(catalog, PakGameCatalog(), scan, libs)``."""
    entries = [_catalog_entry(item, found.games, pak_games) for item in catalog]
    claimed = {(g.store, g.app_id) for entry in entries for g in entry.installs}
    entries.extend(
        _library_entry(game)
        for game in found.games
        if (game.store, game.app_id) not in claimed
    )
    ordered = tuple(sorted(entries, key=shelf_order))
    return GameShelf(ordered, libraries, found.warnings)
