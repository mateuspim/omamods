"""Pick a container name that makes Unreal load it over the mods it clashes with.

The engine reads a ``_<n>_P`` number from the file name (see ``load_rank``), so
renaming ``Fix_P`` to ``Fix_1_P`` lifts it above every plain ``_P`` mod while
keeping the mod's own name readable. A number decides alone, unlike a ``z_``
prefix, whose outcome depends on how the other mods are named.
"""

from collections.abc import Iterable

from omamods.asset_collisions import PATCH_SUFFIX, load_rank


def container_base(name: str) -> str:
    """Strip the patch suffix; e.g. ``container_base('Mod_3_P') == 'Mod'``."""
    base = PATCH_SUFFIX.sub("", name)
    if not base or "/" in base or "\\" in base:
        raise ValueError(
            f"container name={name!r}: expected a file stem such as 'Mod_P'"
        )
    return base


def outranks_all(name: str, competitors: Iterable[str]) -> bool:
    """Tell whether ``name`` already wins; e.g. ``outranks_all('Z_P', ('A_P',))``."""
    rank = load_rank(name)
    return all(rank > load_rank(other) for other in competitors)


def priority_name(name: str, competitors: Iterable[str]) -> str:
    """Rename a container to load over every competitor.

    Example: ``priority_name('Fix_P', ('Outfit_P',)) == 'Fix_1_P'``.
    """
    ranks = [load_rank(other)[0] for other in competitors]
    if not ranks:
        raise ValueError(
            f"container={name!r} competitors=[]: expected at least one clash"
        )
    # '_<n>_P' ranks n + 1 for n >= 1, so n = the best rank beats it outright.
    number = max(1, max(ranks))
    return f"{container_base(name)}_{number}_P"
