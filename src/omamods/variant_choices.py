"""Tell which archive variants exclude each other, and what an install skips.

Variants holding the same file names are alternatives of one item (colours of
an outfit, say): installed together, the game loads both and one silently
wins. Engine-neutral, since it only compares paths below each variant folder.
"""

from collections.abc import Mapping
from pathlib import PurePosixPath

NESTED_ARCHIVE_SUFFIXES = frozenset({".7z", ".rar", ".zip"})


def _files_below(members: tuple[str, ...], variant: str) -> frozenset[str]:
    prefix = f"{variant}/"
    return frozenset(
        member[len(prefix) :].lower()
        for member in members
        if member.startswith(prefix) and not member.endswith("/")
    )


def exclusive_variants(
    members: tuple[str, ...], variants: tuple[str, ...]
) -> Mapping[str, frozenset[str]]:
    """Map each variant to the ones sharing a file name; e.g. ``exclusive_variants(names, ('A', 'B'))``.

    A variant whose files are all inside another's is an add-on, not a rival.
    """
    files = {variant: _files_below(members, variant) for variant in variants}
    return {
        variant: frozenset(
            other
            for other in variants
            if other != variant
            and files[variant] & files[other]
            and not _strict_subset(files[variant], files[other])
            and not _strict_subset(files[other], files[variant])
        )
        for variant in variants
    }


def _strict_subset(small: frozenset[str], big: frozenset[str]) -> bool:
    return small < big


def addon_bases(
    members: tuple[str, ...], variants: tuple[str, ...]
) -> Mapping[str, frozenset[str]]:
    """Map add-on variants to the fuller ones they patch; e.g. ``addon_bases(names, ('Main', 'NoSkirt'))``.

    An add-on overrides some of a main variant's files, as clothing tweaks do.
    """
    files = {variant: _files_below(members, variant) for variant in variants}
    bases = {
        variant: frozenset(
            other
            for other in variants
            if files[variant] and _strict_subset(files[variant], files[other])
        )
        for variant in variants
    }
    return {variant: found for variant, found in bases.items() if found}


def nested_archives(members: tuple[str, ...]) -> tuple[str, ...]:
    """List archives packed inside the archive; e.g. ``nested_archives(('a/b.zip',))``."""
    return tuple(
        member
        for member in members
        if PurePosixPath(member).suffix.lower() in NESTED_ARCHIVE_SUFFIXES
    )
