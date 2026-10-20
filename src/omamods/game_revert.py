"""Revert every install record of one game, in a safe order, past failures.

Two kinds of install depend on revert order:

- RE Engine patch chains: reverting a patch while a loaded one sits above it
  leaves a placeholder pak behind, and nothing removes it once the mod above
  goes too. Reverting the highest patch first and filling gaps once, at the
  end, leaves only the placeholders that mods still installed need.
- Prefix config files (a UE4SS bundle's Engine.ini): an install sets the
  current file aside, so stacked installs must be undone newest first, or an
  older mod's file comes back instead of the game's own.
"""

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path

from omamods.install_records import recorded_file_id
from omamods.pak_games import PakOverlayGame
from omamods.pak_storage import revert_pak_mod
from omamods.re_patch_chain import fill_patch_gaps, patch_number


@dataclass(frozen=True)
class OwnedRecord:
    """One install record and the mod it belongs to; e.g. ``OwnedRecord('nexus', 1, p)``."""

    site: str
    mod_id: int
    record: Path


@dataclass(frozen=True)
class RecordRevert:
    """What reverting one record did: files removed, or why it refused."""

    site: str
    mod_id: int
    file_id: int | None
    removed: int
    error: str = ""


@dataclass(frozen=True)
class GameRevert:
    """Every record's outcome; e.g. ``revert_game_records(sb, owned).removed_files()``."""

    results: tuple[RecordRevert, ...]

    def removed_files(self) -> int:
        """Count game files taken out; e.g. ``outcome.removed_files()``."""
        return sum(result.removed for result in self.results)

    def cleared_mods(self) -> frozenset[tuple[str, int]]:
        """Name mods with files removed; e.g. ``('nexus', 1) in outcome.cleared_mods()``."""
        return frozenset((r.site, r.mod_id) for r in self.results if r.removed)

    def failures(self) -> tuple[RecordRevert, ...]:
        """List refused records; e.g. ``outcome.failures()[0].error``."""
        return tuple(result for result in self.results if result.error)


def highest_patch(record: Path, chain: str | None) -> int:
    """Find a record's top patch number, 0 if none; e.g. ``highest_patch(p, chain)``."""
    if chain is None:
        return 0
    try:
        assets = json.loads(record.read_text(encoding="utf-8"))["assets"]
        paths = [str(asset["relative_path"]) for asset in assets]
    except (OSError, KeyError, TypeError, ValueError):
        return 0  # Revert reports the unreadable record itself.
    numbers = (patch_number(chain, Path(path).name) for path in paths)
    return max((number for number in numbers if number is not None), default=0)


def _installed_at(record: Path) -> int:
    try:
        return record.stat().st_mtime_ns
    except OSError:
        return 0


def revert_order(
    records: Iterable[OwnedRecord], chain: str | None
) -> tuple[OwnedRecord, ...]:
    """Sort highest patch, then newest install, first; e.g. ``revert_order(owned, None)``."""

    def key(owned: OwnedRecord) -> tuple[int, int, str]:
        record = owned.record
        return highest_patch(record, chain), _installed_at(record), str(record)

    return tuple(sorted(records, key=key, reverse=True))


def _file_id(record: Path) -> int | None:
    try:
        return recorded_file_id(record)
    except (OSError, ValueError):
        return None


def _revert_one(
    game: PakOverlayGame, owned: OwnedRecord, removed: list[Path]
) -> RecordRevert:
    file_id = _file_id(owned.record)
    try:
        targets = revert_pak_mod(owned.record, game)
    except (OSError, ValueError) as error:
        return RecordRevert(owned.site, owned.mod_id, file_id, 0, str(error))
    removed.extend(targets)
    return RecordRevert(owned.site, owned.mod_id, file_id, len(targets))


def revert_game_records(
    game: PakOverlayGame, records: Iterable[OwnedRecord]
) -> GameRevert:
    """Revert all, continuing past refusals; e.g. ``revert_game_records(sb, owned)``."""
    removed: list[Path] = []
    results: list[RecordRevert] = []
    try:
        for owned in revert_order(records, game.patch_chain):
            results.append(_revert_one(game, owned, removed))
    finally:
        # Once, after every record: a gap is filled only if a patch still
        # loads above it, as in nexus_workflow._revert_records.
        if game.patch_chain is not None:
            fill_patch_gaps(tuple(removed), game.patch_chain)
    return GameRevert(tuple(results))
