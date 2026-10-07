"""Discover native and Flatpak Steam libraries without changing Steam state."""

from dataclasses import dataclass
from pathlib import Path

from omamods.filesystem import ReadableFiles
from omamods.keyvalues import KeyValues, keyvalues_block, parse_keyvalues


@dataclass(frozen=True)
class LibraryScan:
    """Accessible library roots plus issues that limit discovery certainty."""

    libraries: tuple[Path, ...]
    warnings: tuple[str, ...]


def default_steam_roots(home: Path, xdg_data_home: str | None) -> tuple[Path, ...]:
    """Find conventional roots; e.g. ``default_steam_roots(Path('/home/me'), None)``."""
    share = Path(xdg_data_home) if xdg_data_home else home / ".local/share"
    if not share.is_absolute():
        share = home / ".local/share"
    return (
        share / "Steam",
        home / ".steam/steam",
        home / ".steam/root",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    )


def _library_paths(document: KeyValues) -> tuple[Path, ...]:
    entries = keyvalues_block(document, "libraryfolders")
    paths: list[Path] = []
    for index, entry in entries.items():
        if not index.isdecimal():
            continue
        value = entry.get("path") if isinstance(entry, dict) else entry
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError(
                f"library {index} path={value!r}: expected an absolute path"
            )
        paths.append(Path(value))
    return tuple(paths)


def _root_libraries(root: Path, files: ReadableFiles) -> tuple[Path, ...]:
    manifest = root / "steamapps/libraryfolders.vdf"
    try:
        source = files.read_text(manifest)
    except FileNotFoundError:
        return (root,)
    try:
        return (root, *_library_paths(parse_keyvalues(source)))
    except ValueError as error:
        raise ValueError(f"{manifest}: {error}") from error


def discover_libraries(roots: tuple[Path, ...], files: ReadableFiles) -> LibraryScan:
    """Read each client once; for example, ``discover_libraries((steam_root,), files)``."""
    visited: set[Path] = set()
    candidates: list[Path] = []
    warnings: list[str] = []
    for root in roots:
        root = files.resolve(root)
        if root in visited or not files.is_dir(root):
            continue
        visited.add(root)
        candidates.append(root)
        try:
            candidates.extend(_root_libraries(root, files))
        except (OSError, ValueError) as error:
            warnings.append(str(error))
    return _available_libraries(candidates, warnings, files)


def _available_libraries(
    candidates: list[Path], warnings: list[str], files: ReadableFiles
) -> LibraryScan:
    libraries: list[Path] = []
    canonical = dict.fromkeys(files.resolve(path) for path in candidates)
    for path in canonical:
        if files.is_dir(path / "steamapps"):
            libraries.append(path)
        else:
            warnings.append(
                f"Library {str(path)!r}: expected an accessible steamapps directory"
            )
    if not libraries:
        warnings.append(
            "No accessible Steam libraries found; use --steam-root for a custom installation"
        )
    return LibraryScan(tuple(libraries), tuple(warnings))
