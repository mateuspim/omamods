"""Number RE Engine pak mods as patches and keep the patch chain unbroken.

The engine mounts <chain>.patch_001.pak, _002, ... and stops at the first
missing number. RE7 ships 0-byte patch_002..008 but no patch_001, so a mod
placed after the highest patch never loads; forum fixes rename the mod to
patch_001. A mod at patch_009 still failed behind those 0-byte files while
one at patch_001 loaded, so empty patches count as free slots too: mods take
the lowest missing or empty numbers, and reverting restores what was there.
"""

from dataclasses import replace
from pathlib import Path
import re

from omamods.pak_archive import PlannedAsset
from omamods.re_pak_writer import (
    HEADER,
    PAK_MAJOR_VERSION,
    pak_major_version,
    write_re_pak,
)

HIGHEST_PATCH = 999


def patch_name(chain: str, number: int) -> str:
    """Name one patch; e.g. ``patch_name('re_chunk_000.pak', 9)``."""
    return f"{chain}.patch_{number:03d}.pak"


def patch_number(chain: str, name: str) -> int | None:
    """Read a patch's number, if it is one; e.g. ``patch_number(chain, name)``."""
    found = re.fullmatch(rf"{re.escape(chain)}\.patch_(\d{{3}})\.pak", name)
    return int(found.group(1)) if found else None


def _existing_numbers(folder: Path, chain: str) -> tuple[int, ...]:
    names = (path.name for path in folder.glob(f"{chain}.patch_*.pak"))
    numbers = (patch_number(chain, name) for name in names)
    return tuple(number for number in numbers if number is not None)


def is_empty_patch(path: Path) -> bool:
    """Spot a 0-byte or file-less patch; e.g. ``is_empty_patch(root / name)``."""
    if not path.is_file():
        return False
    size = path.stat().st_size
    if size != HEADER.size:
        return size == 0
    with path.open("rb") as stream:
        header = stream.read(HEADER.size)
    return pak_major_version(header) is not None and HEADER.unpack(header)[4] == 0


def free_patch_numbers(folder: Path, chain: str, count: int) -> tuple[int, ...]:
    """Pick the lowest missing or empty slots; e.g. ``free_patch_numbers(root, c, 2)``."""
    numbers = _existing_numbers(folder, chain)
    taken = {n for n in numbers if not is_empty_patch(folder / patch_name(chain, n))}
    free = [n for n in range(1, HIGHEST_PATCH + 1) if n not in taken][:count]
    if len(free) < count:
        raise ValueError(
            f"{chain} free patch numbers={len(free)}: expected {count} of "
            f"001-{HIGHEST_PATCH}; uninstall mods first"
        )
    return tuple(free)


def number_patches(
    planned: tuple[PlannedAsset, ...], folder: Path, chain: str
) -> tuple[PlannedAsset, ...]:
    """Give each pak its patch slot; e.g. ``number_patches(plan, root, chain)``."""
    numbers = free_patch_numbers(folder, chain, len(planned))
    return tuple(
        replace(
            asset,
            target=Path(patch_name(chain, number)),
            next_patch=False,
            replaces_empty=(folder / patch_name(chain, number)).exists(),
        )
        for number, asset in zip(numbers, planned, strict=True)
    )


def _highest_loaded(folder: Path, chain: str) -> int:
    # Empty patches (Capcom's 0-byte ones, our placeholders) need no chain to
    # reach them, so only a patch with files keeps a lower gap filled.
    loaded = (
        number
        for number in _existing_numbers(folder, chain)
        if not is_empty_patch(folder / patch_name(chain, number))
    )
    return max(loaded, default=0)


def _write_empty_pak(target: Path) -> None:
    # A valid pak with no files, since the chain stops at 0-byte ones.
    with target.open("wb") as stream:
        write_re_pak(stream, ())


def fill_patch_gaps(removed: tuple[Path, ...], chain: str) -> tuple[Path, ...]:
    """Leave empty patches where a gap would cut the chain; e.g. ``fill_patch_gaps(paths, c)``."""
    placeholders: list[Path] = []
    # Highest first, so a removed run at the top of the chain leaves nothing.
    for target in sorted(removed, reverse=True):
        number = patch_number(chain, target.name)
        if number is None:
            continue
        # The revert left the slot missing or restored to 0 bytes; both stop
        # the chain, so upgrade it to a valid empty pak when mods sit above.
        if _highest_loaded(target.parent, chain) > number:
            _write_empty_pak(target)
            placeholders.append(target)
    return tuple(placeholders)


def require_packable_chain(folder: Path, chain: str) -> None:
    """Refuse to pack for other pak formats; e.g. ``require_packable_chain(root, chain)``."""
    # Older builds, such as RE7's non-RT one, use another pak version.
    base = folder / chain
    with base.open("rb") as stream:
        version = pak_major_version(stream.read(HEADER.size))
    if version != PAK_MAJOR_VERSION:
        raise ValueError(
            f"{str(base)!r} pak version={version!r}: expected {PAK_MAJOR_VERSION} "
            "to pack natives/ files"
        )
