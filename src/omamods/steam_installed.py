"""List every game Steam has installed, across all discovered libraries."""

from pathlib import Path
import re

from omamods.filesystem import ReadableFiles
from omamods.installed_games import InstalledGame, InstalledScan, combine_scans
from omamods.keyvalues import KeyValues, keyvalues_block, parse_keyvalues
from omamods.steam_apps import (
    build_id,
    decimal_field,
    install_directory,
    proton_prefix,
    steam_marks_installed,
)
from omamods.steam_libraries import LibraryScan

# Steam installs these runtimes like games; they are never mod targets.
STEAM_TOOL_NAME = re.compile(
    r"^(Proton\b|Steam Linux Runtime\b|Steamworks Common Redistributables$)"
)


def is_steam_tool(name: str) -> bool:
    """Spot runtimes and Proton builds; e.g. ``is_steam_tool('Proton 9.0')``."""
    return STEAM_TOOL_NAME.match(name.strip()) is not None


def _app_name(fields: KeyValues) -> str:
    value = fields.get("name")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"name={value!r}: expected a nonempty game title")
    return value.strip()


def _size(fields: KeyValues) -> int | None:
    value = fields.get("SizeOnDisk")
    return int(value) if isinstance(value, str) and value.isdecimal() else None


def steam_game(fields: KeyValues, library: Path, files: ReadableFiles) -> InstalledGame:
    """Describe one AppState block; e.g. ``steam_game(fields, library, files)``."""
    app_id = decimal_field(fields, "appid")
    install_path = library / "steamapps/common" / install_directory(fields)
    ready = steam_marks_installed(fields) and files.is_dir(install_path)
    return InstalledGame(
        store="Steam",
        app_id=app_id,
        name=_app_name(fields),
        install_path=install_path,
        ready=ready,
        size_bytes=_size(fields),
        library=library,
        build_id=build_id(fields),
        proton_prefix=proton_prefix(library, int(app_id), files),
    )


def _read_manifest(path: Path, library: Path, files: ReadableFiles) -> InstalledGame:
    try:
        fields = keyvalues_block(parse_keyvalues(files.read_text(path)), "AppState")
        return steam_game(fields, library, files)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error


def _library_games(library: Path, files: ReadableFiles) -> InstalledScan:
    games: list[InstalledGame] = []
    warnings: list[str] = []
    for path in files.glob(library / "steamapps", "appmanifest_*.acf"):
        try:
            games.append(_read_manifest(path, library, files))
        except (OSError, ValueError) as error:
            warnings.append(str(error))
    return InstalledScan(tuple(games), tuple(warnings))


def list_steam_games(scan: LibraryScan, files: ReadableFiles) -> InstalledScan:
    """Read every app manifest; e.g. ``list_steam_games(discover_libraries(r, f), f)``."""
    found = combine_scans(*(_library_games(path, files) for path in scan.libraries))
    games: dict[str, InstalledGame] = {}
    for game in found.games:
        if not is_steam_tool(game.name):
            games.setdefault(game.app_id, game)
    return InstalledScan(tuple(games.values()), found.warnings)
