"""Locate ownership records so each staged file of a mod installs independently."""

import json
from pathlib import Path

from omamods.pak_games import PakOverlayGame


def legacy_state_path(root: Path, game: PakOverlayGame, mod_id: int) -> Path:
    """Name the one-per-mod record from before per-file installs.

    Example: ``legacy_state_path(root, cronos, 38)``.
    """
    return root / "state" / game.game_id / f"{mod_id}.json"


def file_state_path(
    root: Path, game: PakOverlayGame, mod_id: int, file_id: int
) -> Path:
    """Name one file's record; e.g. ``file_state_path(root, sb, 1, 7)``."""
    return root / "state" / game.game_id / str(mod_id) / f"{file_id}.json"


def mod_state_records(
    root: Path, game: PakOverlayGame, mod_id: int
) -> tuple[Path, ...]:
    """List every record of a mod; e.g. ``mod_state_records(root, sb, 1)``."""
    legacy = legacy_state_path(root, game, mod_id)
    per_file = sorted((legacy.parent / str(mod_id)).glob("*.json"))
    return ((legacy,) if legacy.is_file() else ()) + tuple(per_file)


def recorded_file_id(record: Path) -> int:
    """Read which Nexus file a record installed; e.g. ``recorded_file_id(path)``."""
    if record.stem.isdecimal() and record.parent.name.isdecimal():
        return int(record.stem)
    try:
        file_id = json.loads(record.read_text(encoding="utf-8"))["file_id"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"install state={str(record)!r}: expected a file_id field"
        ) from error
    if type(file_id) is not int:
        raise ValueError(f"install state file_id={file_id!r}: expected an integer")
    return file_id


def installed_file_ids(root: Path, game: PakOverlayGame, mod_id: int) -> frozenset[int]:
    """Report installed files of a mod; e.g. ``installed_file_ids(root, sb, 1)``."""
    return frozenset(
        recorded_file_id(record) for record in mod_state_records(root, game, mod_id)
    )
