"""List Epic, GOG, Amazon, and sideloaded games that Heroic Games Launcher installed."""

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path

from omamods.filesystem import ReadableFiles
from omamods.installed_games import InstalledGame, InstalledScan, combine_scans

HeroicEntry = dict[str, object]


@dataclass(frozen=True)
class HeroicRecord:
    """One Heroic install file and how its entries become games."""

    subpath: str
    store: str
    entries: Callable[[object], tuple[HeroicEntry, ...]]
    app_id_key: str
    path_key: str


def default_heroic_roots(home: Path, xdg_config_home: str | None) -> tuple[Path, ...]:
    """Find native and Flatpak configs; e.g. ``default_heroic_roots(home, None)``."""
    config = Path(xdg_config_home) if xdg_config_home else home / ".config"
    if not config.is_absolute():
        config = home / ".config"
    return (
        config / "heroic",
        home / ".var/app/com.heroicgameslauncher.hgl/config/heroic",
    )


def _mappings(value: object, field: str) -> tuple[HeroicEntry, ...]:
    if not isinstance(value, list) or not all(isinstance(i, dict) for i in value):
        raise ValueError(f"{field}={value!r}: expected a list of objects")
    return tuple(value)


def _epic_entries(document: object) -> tuple[HeroicEntry, ...]:
    if not isinstance(document, dict):
        raise ValueError(f"installed={document!r}: expected an object keyed by app")
    return _mappings(list(document.values()), "installed")


def _gog_entries(document: object) -> tuple[HeroicEntry, ...]:
    if not isinstance(document, dict):
        raise ValueError(f"document={document!r}: expected {{'installed': [...]}}")
    return _mappings(document.get("installed", []), "installed")


def _amazon_entries(document: object) -> tuple[HeroicEntry, ...]:
    return _mappings(document, "installed")


def _sideload_entries(document: object) -> tuple[HeroicEntry, ...]:
    if not isinstance(document, dict):
        raise ValueError(f"document={document!r}: expected {{'games': [...]}}")
    games = _mappings(document.get("games", []), "games")
    return tuple(game for game in games if game.get("is_installed") is True)


HEROIC_RECORDS: tuple[HeroicRecord, ...] = (
    HeroicRecord(
        "legendaryConfig/legendary/installed.json",
        "Epic",
        _epic_entries,
        "app_name",
        "install_path",
    ),
    HeroicRecord(
        "gog_store/installed.json", "GOG", _gog_entries, "appName", "install_path"
    ),
    HeroicRecord(
        "nile_config/nile/installed.json", "Amazon", _amazon_entries, "id", "path"
    ),
    HeroicRecord(
        "sideload_apps/library.json",
        "Sideloaded",
        _sideload_entries,
        "app_name",
        "folder_name",
    ),
)


def _text(entry: HeroicEntry, key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}={value!r}: expected a nonempty string")
    return value.strip()


def _absolute_path(entry: HeroicEntry, key: str) -> Path:
    path = Path(_text(entry, key))
    if not path.is_absolute():
        raise ValueError(f"{key}={str(path)!r}: expected an absolute path")
    return path


def _size(entry: HeroicEntry) -> int | None:
    # Legendary stores bytes; GOG stores display text such as "9.69 GiB".
    value = entry.get("install_size", entry.get("size"))
    return value if type(value) is int and value >= 0 else None


def heroic_game(
    entry: HeroicEntry, record: HeroicRecord, files: ReadableFiles
) -> InstalledGame:
    """Describe one install entry; e.g. ``heroic_game(entry, HEROIC_RECORDS[0], f)``."""
    install_path = _absolute_path(entry, record.path_key)
    title = entry.get("title")
    name = title.strip() if isinstance(title, str) and title.strip() else None
    return InstalledGame(
        store=record.store,
        app_id=_text(entry, record.app_id_key),
        name=name or install_path.name,
        install_path=install_path,
        ready=files.is_dir(install_path),
        size_bytes=_size(entry),
    )


def _record_entries(
    root: Path, record: HeroicRecord, files: ReadableFiles
) -> tuple[HeroicEntry, ...]:
    try:
        source = files.read_text(root / record.subpath)
    except FileNotFoundError:
        return ()
    return record.entries(json.loads(source))


def _games_in_record(
    root: Path, record: HeroicRecord, files: ReadableFiles
) -> InstalledScan:
    try:
        entries = _record_entries(root, record, files)
        games = tuple(
            heroic_game(entry, record, files)
            for entry in entries
            if entry.get("is_dlc") is not True
        )
    except (OSError, ValueError) as error:
        return InstalledScan((), (f"{root / record.subpath}: {error}",))
    return InstalledScan(games, ())


def list_heroic_games(roots: tuple[Path, ...], files: ReadableFiles) -> InstalledScan:
    """Read Heroic's install records; e.g. ``list_heroic_games(roots, files)``."""
    present = (root for root in roots if files.is_dir(root))
    return combine_scans(
        *(
            _games_in_record(root, record, files)
            for root in present
            for record in HEROIC_RECORDS
        )
    )
