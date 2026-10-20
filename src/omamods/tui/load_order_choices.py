"""Plan and apply load-order renames for the mods screen's P and :load-default."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from omamods.asset_collisions import ModContainer
from omamods.container_rename import (
    container_moves,
    rename_container,
    require_unreal_paks,
)
from omamods.install_records import mod_state_records, recorded_file_id
from omamods.installed_containers import recorded_containers, recorded_stems
from omamods.load_order_store import (
    load_order_path,
    read_load_order,
    remember_choice,
    write_load_order,
)
from omamods.load_priority import outranks_all, priority_name
from omamods.pak_games import PakOverlayGame
from omamods.staging import StagedMod

if TYPE_CHECKING:
    from omamods.tui.service import ModsService


@dataclass(frozen=True)
class ContainerRename:
    """One container to rename, and the containers it will then load over."""

    record: Path
    old_stem: str
    new_stem: str
    wins: tuple[str, ...] = ()


def container_stem(record: Path, name: str) -> str:
    """Find a container's Paks-relative stem; e.g. ``container_stem(state, 'Fix_P')``."""
    stems = recorded_stems(record).get(name, frozenset())
    if len(stems) != 1:
        raise ValueError(
            f"container={name!r} in {str(record)!r}: expected one file stem, "
            f"got {sorted(stems)}"
        )
    return next(iter(stems))


def promotion(
    record: Path, mine: ModContainer, others: tuple[ModContainer, ...]
) -> ContainerRename | None:
    """Rename ``mine`` to beat its clashes, or None when it wins already.

    Example: ``promotion(state, fix, (outfit,))`` renames Fix_P to Fix_1_P.
    """
    rivals = tuple(other for other in others if other.packages & mine.packages)
    names = tuple(rival.name for rival in rivals)
    if not rivals or outranks_all(mine.name, names):
        return None
    stem = PurePosixPath(container_stem(record, mine.name))
    new_stem = stem.with_name(priority_name(mine.name, names)).as_posix()
    wins = tuple(f"{rival.name} ({rival.owner})" for rival in rivals)
    return ContainerRename(record, stem.as_posix(), new_stem, wins)


def default_renames(record: Path) -> tuple[ContainerRename, ...]:
    """Renames back to the archive's names; e.g. ``default_renames(state)``."""
    choices = read_load_order(load_order_path(record))
    current = {stem for stems in recorded_stems(record).values() for stem in stems}
    return tuple(
        ContainerRename(record, chosen, original)
        for original, chosen in sorted(choices.items())
        if chosen in current
    )


class LoadOrderChoices:
    """Rename a file's containers to load last; e.g. ``service.load_order.to_load_last(g, m, 7)``."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service

    def _file_records(
        self, game: PakOverlayGame, mod: StagedMod, file_id: int
    ) -> tuple[Path, ...]:
        root = self.service.state_root(mod.site)
        records = mod_state_records(root, game, mod.mod_id)
        return tuple(r for r in records if recorded_file_id(r) == file_id)

    def _record_containers(
        self, owner: str, records: tuple[Path, ...]
    ) -> tuple[tuple[Path, ModContainer], ...]:
        indexes = self.service.conflicts.indexes
        found: list[tuple[Path, ModContainer]] = []
        for record in records:
            containers = indexes.containers(owner, recorded_containers(record))
            found.extend((record, container) for container in containers)
        return tuple(found)

    def _installed_except(
        self, game: PakOverlayGame, skip: tuple[Path, ...]
    ) -> tuple[ModContainer, ...]:
        others: list[ModContainer] = []
        for mod in self.service.staged_mods(game):
            root = self.service.state_root(mod.site)
            records = mod_state_records(root, game, mod.mod_id)
            kept = tuple(record for record in records if record not in skip)
            others.extend(c for _, c in self._record_containers(mod.title, kept))
        return tuple(others)

    def to_load_last(
        self, game: PakOverlayGame, mod: StagedMod, file_id: int
    ) -> tuple[ContainerRename, ...]:
        """Renames that make a file win its clashes; e.g. ``to_load_last(mgs, hero, 7)``."""
        require_unreal_paks(game)
        records = self._file_records(game, mod, file_id)
        others = self._installed_except(game, records)
        found = (
            promotion(record, mine, others)
            for record, mine in self._record_containers(mod.title, records)
        )
        return tuple(rename for rename in found if rename is not None)

    def to_default(
        self, game: PakOverlayGame, mod: StagedMod, file_id: int
    ) -> tuple[ContainerRename, ...]:
        """Renames back to the archive's names; e.g. ``to_default(mgs, hero, 7)``."""
        require_unreal_paks(game)
        records = self._file_records(game, mod, file_id)
        return tuple(r for record in records for r in default_renames(record))

    def describe(
        self, game: PakOverlayGame, renames: tuple[ContainerRename, ...]
    ) -> str:
        """List old -> new files and the clashes won; e.g. ``describe(mgs, renames)``."""
        lines: list[str] = []
        for rename in renames:
            moves = container_moves(
                rename.record, game, rename.old_stem, rename.new_stem
            )
            lines.extend(f"  {move.old} -> {move.new}" for move in moves)
            lines.extend(f"  now loads over {win}" for win in rename.wins)
        return "\n".join(lines)

    def apply(self, game: PakOverlayGame, renames: tuple[ContainerRename, ...]) -> int:
        """Rename on disk and remember the choice; e.g. ``apply(mgs, renames)``."""
        moved = 0
        for rename in renames:
            moved += len(self._apply_one(game, rename))
        return moved

    def _apply_one(
        self, game: PakOverlayGame, rename: ContainerRename
    ) -> tuple[str, ...]:
        old, new = rename.old_stem, rename.new_stem
        moves = rename_container(rename.record, game, old, new)
        choices_path = load_order_path(rename.record)
        try:
            choices = read_load_order(choices_path)
            write_load_order(choices_path, remember_choice(choices, old, new))
        except BaseException:
            rename_container(rename.record, game, new, old)  # Keep both in step.
            raise
        return tuple(move.new for move in moves)
