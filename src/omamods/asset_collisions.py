"""Find mods that replace the same Unreal package, and which one the game shows.

Two containers that both carry a package fight over it; Unreal reads the one
it mounted with the higher priority. Priority follows the engine's pak order:
``_P`` patch paks outrank plain ones, a ``_<n>_P`` number raises a patch further,
and between equals the name that sorts later (ignoring case) is mounted first
and wins. That last rule is why modders prefix ``z_`` to load last.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
import re

PATCH_SUFFIX = re.compile(r"(?:_([0-9]+))?_p$", re.IGNORECASE)
# Mod kits add a PrimaryAssetLabel to every mod so it cooks into its own chunk;
# all mods ship the same one and it changes nothing in game.
PLACEHOLDER_PACKAGE = re.compile(r"(?:^|/)label_[^/]*$")
PACKAGE_SUFFIXES = frozenset({".uasset", ".uexp", ".ubulk", ".umap", ".uptnl"})


@dataclass(frozen=True)
class ModContainer:
    """One installed or planned container and the packages it carries."""

    owner: str
    name: str
    packages: frozenset[str]


@dataclass(frozen=True)
class AssetCollision:
    """Packages two containers both carry; ``shown`` is the one the game reads."""

    shown: ModContainer
    hidden: ModContainer
    packages: tuple[str, ...]


def entry_key(path: str) -> str | None:
    """Name what a file replaces; e.g. ``entry_key('../../../G/Content/A.uasset')``."""
    pure = PurePosixPath(path.replace("\\", "/"))
    # A package's .uasset, .uexp, and .ubulk travel together, so key by package;
    # sound banks, .locres, and configs replace whole files.
    if pure.suffix.lower() in PACKAGE_SUFFIXES:
        pure = pure.with_suffix("")
    key = "/".join(p for p in pure.parts if p not in ("..", ".")).lower()
    return None if PLACEHOLDER_PACKAGE.search(key) else key


def container_entries(paths: Iterable[str]) -> frozenset[str]:
    """Collect what a container replaces; e.g. ``container_entries(paths)``."""
    keys = (entry_key(path) for path in paths)
    return frozenset(key for key in keys if key is not None)


def load_rank(name: str) -> tuple[int, str]:
    """Rank a container by Unreal's pak order; e.g. ``load_rank('Mod_P')``."""
    match = PATCH_SUFFIX.search(name)
    if match is None:
        return 0, name.lower()
    number = int(match.group(1)) if match.group(1) else 0
    # Engine: a '_<n>_P' with n >= 1 counts n + 1; any other '_P' counts 1.
    return (number + 1 if number >= 1 else 1), name.lower()


def collision_between(
    first: ModContainer, second: ModContainer
) -> AssetCollision | None:
    """Compare two containers; e.g. ``collision_between(mine, theirs)``."""
    shared = tuple(sorted(first.packages & second.packages))
    if not shared:
        return None
    if load_rank(first.name) >= load_rank(second.name):
        return AssetCollision(first, second, shared)
    return AssetCollision(second, first, shared)


def find_collisions(
    mine: tuple[ModContainer, ...], others: tuple[ModContainer, ...]
) -> tuple[AssetCollision, ...]:
    """Every clash between two sets; e.g. ``find_collisions(outfit, installed)``."""
    found = (collision_between(ours, theirs) for ours in mine for theirs in others)
    return tuple(collision for collision in found if collision is not None)


def internal_collisions(mine: tuple[ModContainer, ...]) -> tuple[AssetCollision, ...]:
    """Clashes between one mod's own files; e.g. ``internal_collisions(outfit)``."""
    found = (
        collision_between(first, mine[later])
        for index, first in enumerate(mine)
        for later in range(index + 1, len(mine))
    )
    return tuple(collision for collision in found if collision is not None)


def short_package(key: str) -> str:
    """Trim a package to its name; e.g. ``short_package('g/content/a/b') == 'b'``."""
    return key.rsplit("/", 1)[-1]


def describe_collision(collision: AssetCollision, owner: str) -> str:
    """Explain a clash from ``owner``'s side; e.g. ``describe_collision(c, 'Outfit')``."""
    count = len(collision.packages)
    sample = ", ".join(short_package(key) for key in collision.packages[:3])
    more = f", +{count - 3} more" if count > 3 else ""
    if collision.shown.owner == collision.hidden.owner:
        verdict = "two of its files overlap"
    elif collision.shown.owner == owner:
        verdict = f"overrides {collision.hidden.owner}"
    else:
        verdict = f"hidden by {collision.shown.owner}"
    order = f"{collision.shown.name} loads over {collision.hidden.name}"
    return f"{verdict}: {count} asset(s) ({sample}{more}); {order}"
