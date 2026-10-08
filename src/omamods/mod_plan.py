"""Decide which of a mod's files to download and install together.

Nexus categories: MAIN, UPDATE, OPTIONAL, MISCELLANEOUS, OLD_VERSION, ARCHIVED,
DELETED; hand-downloaded archives are STAGED. Optional files are often
alternatives to each other, so "install mod" leaves them for the user to pick.
"""

from dataclasses import dataclass

from omamods.nexus_api import STALE_CATEGORIES, NexusFile
from omamods.pak_archive import PlannedAsset
from omamods.staging import StagedMod

NOT_DEFAULT_INSTALL = STALE_CATEGORIES | {"OPTIONAL"}


@dataclass(frozen=True)
class FilePlan:
    """One file's chosen variant and the game paths it would create."""

    file: NexusFile
    option: str | None
    assets: tuple[PlannedAsset, ...]


def preselected_download(file: NexusFile) -> bool:
    """Tick current files in the picker; e.g. ``preselected_download(file)``."""
    return file.category not in STALE_CATEGORIES


def default_installs(mod: StagedMod) -> tuple[NexusFile, ...]:
    """Files "install mod" takes; for example, ``default_installs(staged)``."""
    return tuple(
        file
        for file in mod.files
        if file.file_id in mod.archives
        and file.file_id not in mod.installed
        and file.category not in NOT_DEFAULT_INSTALL
    )


def conflicting_targets(plans: tuple[FilePlan, ...]) -> tuple[str, ...]:
    """Describe paths two files would both write; e.g. ``conflicting_targets(p)``."""
    owners: dict[str, str] = {}
    conflicts: list[str] = []
    for plan in plans:
        # Each RE Engine patch gets its own new slot, so it never collides.
        for asset in (a for a in plan.assets if not a.next_patch):
            target = asset.target.as_posix()
            if target in owners:
                conflicts.append(
                    f"{target}: {owners[target]} and {plan.file.file_name}"
                )
            owners.setdefault(target, plan.file.file_name)
    return tuple(conflicts)


def describe_plans(plans: tuple[FilePlan, ...], folder: str = "Paks") -> str:
    """List what will be written; for example, ``describe_plans(plans, 'Paks')``."""
    lines: list[str] = []
    for plan in plans:
        variant = f" (variant {plan.option})" if plan.option else ""
        lines.append(f"{plan.file.file_name}{variant}")
        lines.extend(_target_line(asset, folder) for asset in plan.assets)
    return "\n".join(lines)


def _target_line(asset: PlannedAsset, folder: str) -> str:
    if asset.packed:
        return (
            f"  next free patch_NNN.pak <- {len(asset.packed)} natives/ files, packed"
        )
    if asset.next_patch:
        return f"  next free patch_NNN.pak <- {asset.target.as_posix()}"
    return f"  {folder}/{asset.target.as_posix()}"
