"""Tell the mods screen which installed mods replace the same game assets."""

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING

from omamods.asset_collisions import (
    AssetCollision,
    ModContainer,
    find_collisions,
    internal_collisions,
)
from omamods.install_records import mod_state_records
from omamods.installed_containers import (
    INDEX_READERS,
    ContainerIndexes,
    recorded_containers,
)
from omamods.mod_plan import FilePlan
from omamods.pak_archive import PlannedAsset
from omamods.pak_games import PakOverlayGame
from omamods.staging import StagedMod

if TYPE_CHECKING:
    from omamods.tui.service import ModsService

ModKey = tuple[str, int]


@dataclass(frozen=True)
class CollisionReport:
    """Clashes found, and containers whose index could not be read."""

    collisions: tuple[AssetCollision, ...]
    unreadable: tuple[str, ...] = ()


def mod_key(mod: StagedMod) -> ModKey:
    """Tell mods of different sites apart; e.g. ``mod_key(staged)``."""
    return mod.site, mod.mod_id


class AssetConflicts:
    """Compare mods' containers; e.g. ``service.conflicts.for_mod(game, mod)``."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service
        self.indexes = ContainerIndexes(service.host.open_ranges)

    def _installed_files(self, game: PakOverlayGame, mod: StagedMod) -> list[Path]:
        root = self.service.state_root(mod.site)
        records = mod_state_records(root, game, mod.mod_id)
        return [path for record in records for path in recorded_containers(record)]

    def _read(
        self, owner: str, files: list[Path], unreadable: list[str]
    ) -> tuple[ModContainer, ...]:
        try:
            return self.indexes.containers(owner, files)
        except (OSError, ValueError) as error:
            unreadable.append(f"{owner}: {error}")
            return ()

    def _others(
        self, game: PakOverlayGame, skip: ModKey, unreadable: list[str]
    ) -> tuple[ModContainer, ...]:
        others: list[ModContainer] = []
        for mod in self.service.staged_mods(game):
            if mod.installed and mod_key(mod) != skip:
                files = self._installed_files(game, mod)
                others.extend(self._read(mod.title, files, unreadable))
        return tuple(others)

    def _report(
        self,
        mine: tuple[ModContainer, ...],
        others: tuple[ModContainer, ...],
        unreadable: list[str],
    ) -> CollisionReport:
        found = internal_collisions(mine) + find_collisions(mine, others)
        return CollisionReport(found, tuple(unreadable))

    def for_mod(self, game: PakOverlayGame, mod: StagedMod) -> CollisionReport:
        """Clashes of an installed mod; e.g. ``conflicts.for_mod(mgs, outfit)``."""
        if not mod.installed:
            return CollisionReport(())
        unreadable: list[str] = []
        mine = self._read(mod.title, self._installed_files(game, mod), unreadable)
        others = self._others(game, mod_key(mod), unreadable) if mine else ()
        return self._report(mine, others, unreadable)

    def for_plans(
        self, game: PakOverlayGame, mod: StagedMod, plans: tuple[FilePlan, ...]
    ) -> CollisionReport:
        """Clashes an install would cause; e.g. ``conflicts.for_plans(mgs, m, p)``."""
        unreadable: list[str] = []
        with tempfile.TemporaryDirectory(prefix="omamods-index-") as folder:
            try:
                files = self._extract_planned(mod, plans, Path(folder))
            except (OSError, ValueError) as error:
                # A failed check must not block the install it only advises on.
                return CollisionReport((), (f"{mod.title}: {error}",))
            mine = self._read(mod.title, files, unreadable)
            if not mine:
                return CollisionReport((), tuple(unreadable))
            others = self._others(game, mod_key(mod), unreadable)
            kept = self._kept_files(game, mod, mine, unreadable)
            return self._report(mine, kept + others, unreadable)

    def _kept_files(
        self,
        game: PakOverlayGame,
        mod: StagedMod,
        mine: tuple[ModContainer, ...],
        unreadable: list[str],
    ) -> tuple[ModContainer, ...]:
        # The mod's other installed files stay; a reinstalled one is replaced.
        planned = {container.name for container in mine}
        installed = self._read(mod.title, self._installed_files(game, mod), unreadable)
        return tuple(c for c in installed if c.name not in planned)

    def _extract_planned(
        self, mod: StagedMod, plans: tuple[FilePlan, ...], folder: Path
    ) -> list[Path]:
        files: list[Path] = []
        for number, plan in enumerate(plans):
            archive = mod.archives[plan.file.file_id]
            # One folder per plan keeps two variants' same-named files apart.
            target_folder = folder / str(number)
            target_folder.mkdir()
            files.extend(
                self._extract_index(archive, asset, target_folder)
                for asset in plan.assets
                if asset.target.suffix.lower() in INDEX_READERS
            )
        return files

    def _extract_index(self, archive: Path, asset: PlannedAsset, folder: Path) -> Path:
        target = folder / asset.target.name
        with target.open("wb") as stream:
            self.service.host.reader.copy_member(archive, asset.member, stream)
        return target
