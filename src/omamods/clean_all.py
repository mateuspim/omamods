"""Reset every game to no mods: uninstall tracked mods, set aside the rest.

Combines a game's "uninstall all" (U) and "set aside untracked" (X) across
the whole library. Nothing is deleted outright: tracked files are copied into
the dated removed folder before their records revert them, and untracked files
move there, both with a manifest of their original paths.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from omamods.empty_folders import prune_empty_parents
from omamods.game_revert import GameRevert, OwnedRecord, revert_game_records
from omamods.install_records import mod_state_records
from omamods.pak_games import PakOverlayGame
from omamods.red_archive import RED_SHIPPED_FOLDERS
from omamods.tracked_backup import keep_copies
from omamods.untracked_clean import set_aside
from omamods.untracked_mods import record_files

PREVIEW_FILES = 5
CLEAN_NOTE = (
    "Every file goes to a dated 'removed' folder in OmaMods storage with "
    "a moved.json of its original path; nothing is deleted. Tracked mods "
    "are copied there before they are uninstalled, and folders left empty "
    "are removed. If a game breaks, verify its files in Steam."
)


@dataclass(frozen=True)
class GameClean:
    """What cleaning one game touches; e.g. ``GameClean('sb', 'SB', sb, (), (), ())``."""

    key: str
    name: str
    game: PakOverlayGame
    records: tuple[OwnedRecord, ...]
    tracked: tuple[Path, ...]
    untracked: tuple[Path, ...]


@dataclass(frozen=True)
class CleanOutcome:
    """What a clean did; e.g. ``outcome.failures`` lists records that refused."""

    folder: Path
    set_aside: int
    uninstalled: int
    failures: tuple[str, ...]
    pruned: int


def recorded_mod_ids(state: Path) -> tuple[int, ...]:
    """List mods with records under a game's state folder; e.g. ``recorded_mod_ids(root / 'state' / 'sb')``."""
    if not state.is_dir():
        return ()
    # Per-file records sit in <mod_id>/; old ones are <mod_id>.json.
    stems = (p.name if p.is_dir() else p.stem for p in state.iterdir())
    return tuple(sorted({int(stem) for stem in stems if stem.isdecimal()}))


def site_records(
    roots: Mapping[str, Path], game: PakOverlayGame
) -> tuple[OwnedRecord, ...]:
    """Find a game's install records on every site; e.g. ``site_records({'nexus': root}, sb)``."""
    found: list[OwnedRecord] = []
    for site, root in roots.items():
        for mod_id in recorded_mod_ids(root / "state" / game.game_id):
            records = mod_state_records(root, game, mod_id)
            found.extend(OwnedRecord(site, mod_id, record) for record in records)
    return tuple(found)


def plan_game(
    key: str,
    name: str,
    game: PakOverlayGame,
    roots: Mapping[str, Path],
    untracked: tuple[Path, ...],
) -> GameClean:
    """Gather one game's records and stray files; e.g. ``plan_game('sb', 'SB', sb, roots, ())``."""
    records = site_records(roots, game)
    owned = (path for owned in records for path in record_files(owned.record))
    tracked = tuple(sorted({path for path in owned if path.is_file()}))
    return GameClean(key, name, game, records, tracked, untracked)


def plan_clean(
    games: Mapping[str, PakOverlayGame],
    names: Mapping[str, str],
    roots: Mapping[str, Path],
    untracked: Mapping[str, tuple[Path, ...]],
) -> tuple[GameClean, ...]:
    """Plan every game with something to clean; e.g. ``plan_clean(games, names, roots, {})``."""
    planned = (
        plan_game(key, names.get(key, key), game, roots, untracked.get(key, ()))
        for key, game in games.items()
    )
    return tuple(g for g in planned if g.records or g.tracked or g.untracked)


def _file_lines(label: str, files: tuple[Path, ...]) -> list[str]:
    if not files:
        return []
    lines = [f"  {label}: {len(files)} file(s)"]
    lines.extend(f"      {file}" for file in files[:PREVIEW_FILES])
    if len(files) > PREVIEW_FILES:
        lines.append(f"      … and {len(files) - PREVIEW_FILES} more")
    return lines


def describe_clean(plan: tuple[GameClean, ...]) -> str:
    """List what cleaning moves, game by game; e.g. ``describe_clean(plan)``."""
    lines: list[str] = []
    for game in plan:
        lines.append(f"{game.name}: {len(game.records)} install record(s)")
        lines.extend(_file_lines("uninstall", game.tracked))
        lines.extend(_file_lines("set aside, no record", game.untracked))
    lines.append("\n" + CLEAN_NOTE)
    return "\n".join(lines)


def protected_folders(game: PakOverlayGame) -> frozenset[Path]:
    """Folders a clean never removes, empty or not; e.g. ``protected_folders(cyberpunk)``."""
    root = game.install_root
    if root is None:
        return frozenset()
    shipped = (root / name for name in RED_SHIPPED_FOLDERS) if game.redengine else ()
    return frozenset({root / game.paks_subpath, *shipped})


def _prune(game: GameClean) -> int:
    root = game.game.install_root
    if root is None:
        return 0
    files = (*game.tracked, *game.untracked)
    return prune_empty_parents(files, root, protected_folders(game.game))


def _revert(game: GameClean, records: tuple[OwnedRecord, ...]) -> GameRevert:
    return revert_game_records(game.game, records)


def _uninstall(game: GameClean) -> tuple[int, tuple[str, ...]]:
    outcome = _revert(game, game.records)
    refused = tuple(owned for owned in game.records if owned.record.is_file())
    if not refused:
        return outcome.removed_files(), ()
    # A changed file refuses revert; its copy is already kept, so take it out
    # and revert again, which then skips the hash check for missing files.
    for owned in refused:
        for path in record_files(owned.record):
            path.unlink(missing_ok=True)
    retry = _revert(game, refused)
    failures = tuple(
        f"{game.name} mod {failure.mod_id}: {failure.error}"
        for failure in retry.failures()
    )
    return outcome.removed_files() + retry.removed_files(), failures


def run_clean(plan: tuple[GameClean, ...], destination: Path) -> CleanOutcome:
    """Clean every planned game; e.g. ``run_clean(plan, root / 'removed' / stamp)``."""
    # Strays first: a patch chain then holds only tracked patches, which
    # revert highest first and leave no gap-filling placeholders behind.
    strays = {g.key: tuple(f for f in g.untracked if f.is_file()) for g in plan}
    strays = {key: files for key, files in strays.items() if files}
    moved = set_aside(strays, destination / "untracked")[0] if strays else 0
    keep_copies({g.key: g.tracked for g in plan}, destination / "tracked")
    removed, failures = 0, ()
    for game in plan:
        count, failed = _uninstall(game)
        removed, failures = removed + count, failures + failed
    pruned = sum(_prune(game) for game in plan)
    return CleanOutcome(destination, moved, removed, failures, pruned)


def summarize_clean(outcome: CleanOutcome) -> str:
    """Say what a clean did; e.g. ``notify(summarize_clean(outcome))``."""
    summary = (
        f"Uninstalled {outcome.uninstalled} file(s), set aside "
        f"{outcome.set_aside}, removed {outcome.pruned} empty folder(s). "
        f"Copies are in {outcome.folder}"
    )
    if not outcome.failures:
        return summary
    return f"{summary}\n{len(outcome.failures)} failed:\n" + "\n".join(outcome.failures)
