"""List mod files a game keeps outside a mods folder.

Cyberpunk and MGSV have no mods folder: frameworks and plugins sit among the
game's own files. Each lister names only locations the game does not ship, so
a file it returns is a mod's, and nothing from the game's own tree.
"""

from pathlib import Path

from omamods.asi_archive import ASI_LOADER_DLLS, ASI_PLUGIN_FOLDERS, ASI_SUFFIX
from omamods.ue4ss_archive import (
    BINARIES_FROM_PAKS,
    UE4SS_CORE,
    UE4SS_FOLDER,
    UE4SS_PROXY_DLLS,
)

# Folders and loader DLLs that vanilla Cyberpunk does not ship.
RED_MOD_FOLDERS = (
    "archive/pc/mod",
    "r6/scripts",
    "r6/tweaks",
    "red4ext",
    "bin/x64/plugins",
    "mods",
)
RED_LOADER_FILES = ("bin/x64/winmm.dll", "bin/x64/version.dll")


def _files_below(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.is_file()] if folder.is_dir() else []


def red_loose_files(game_root: Path) -> tuple[Path, ...]:
    """List framework and mod files in a REDengine folder; e.g. ``red_loose_files(root)``."""
    found: list[Path] = []
    for folder in RED_MOD_FOLDERS:
        found.extend(_files_below(game_root / folder))
    found.extend(p for p in (game_root / f for f in RED_LOADER_FILES) if p.is_file())
    return tuple(sorted(found))


def _insensitive_children(root: Path, names: frozenset[str]) -> list[Path]:
    return [p for p in root.iterdir() if p.name.lower() in names]


def asi_loose_files(exe_folder: Path) -> tuple[Path, ...]:
    """List ASI plugins and their loader; e.g. ``asi_loose_files(game_root)``."""
    if not exe_folder.is_dir():
        return ()
    plugins = [p for p in exe_folder.glob(f"*{ASI_SUFFIX}") if p.is_file()]
    for folder in _insensitive_children(exe_folder, ASI_PLUGIN_FOLDERS):
        plugins.extend(p for p in _files_below(folder) if p.suffix in (".asi", ".ini"))
    if not plugins:
        return ()
    settings = [p.with_suffix(".ini") for p in plugins if p.parent == exe_folder]
    loaders = [exe_folder / n for n in sorted(ASI_LOADER_DLLS)]
    found = {*plugins, *settings, *loaders}
    return tuple(sorted(p for p in found if p.is_file()))


def ue4ss_loose_files(paks: Path) -> tuple[Path, ...]:
    """List UE4SS files beside the game executable; e.g. ``ue4ss_loose_files(paks)``."""
    binaries = (paks / BINARIES_FROM_PAKS).resolve()
    if not (binaries / UE4SS_CORE).is_file():
        return ()
    proxies = (binaries / dll for dll in sorted(UE4SS_PROXY_DLLS))
    found = _files_below(binaries / UE4SS_FOLDER)
    found.extend(p for p in proxies if p.is_file())
    return tuple(sorted(found))
