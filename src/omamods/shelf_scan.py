"""Scan Steam and Heroic, then promote Unreal and RE Engine games OmaMods can mod."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from omamods.filesystem import ReadableFiles
from omamods.game_shelf import GameShelf, build_shelf
from omamods.heroic_games import list_heroic_games
from omamods.installed_games import InstalledScan, combine_scans
from omamods.manifests import GameManifest
from omamods.nexus_games import NexusGameDirectory
from omamods.pak_detection import promote_pak_games
from omamods.pak_games import PakGameCatalog
from omamods.steam_installed import list_steam_games
from omamods.steam_libraries import discover_libraries


@dataclass(frozen=True)
class ShelfSources:
    """Where to look for games; injected so tests can use fake files."""

    catalog: Callable[[], tuple[GameManifest, ...]]
    steam_roots: tuple[Path, ...]
    heroic_roots: tuple[Path, ...]
    files: ReadableFiles
    pak_games: PakGameCatalog
    nexus_games: Callable[[], NexusGameDirectory]


def scan_shelf(sources: ShelfSources) -> GameShelf:
    """Look in Steam and Heroic; for example, ``scan_shelf(sources)``."""
    files = sources.files
    libraries = discover_libraries(sources.steam_roots, files)
    steam = list_steam_games(libraries, files)
    heroic = list_heroic_games(sources.heroic_roots, files)
    found = combine_scans(InstalledScan((), libraries.warnings), steam, heroic)
    catalog = sources.catalog()
    shelf = build_shelf(catalog, sources.pak_games, found, libraries.libraries)
    return promote_pak_games(shelf, files, sources.nexus_games())
