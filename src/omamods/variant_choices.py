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
    """Map each variant to the ones sharing a file name; e.g. ``exclusive_variants(names, ('A', 'B'))``."""
    files = {variant: _files_below(members, variant) for variant in variants}
    return {
        variant: frozenset(
            other
            for other in variants
            if other != variant and files[variant] & files[other]
        )
        for variant in variants
    }


def nested_archives(members: tuple[str, ...]) -> tuple[str, ...]:
    """List archives packed inside the archive; e.g. ``nested_archives(('a/b.zip',))``."""
    return tuple(
        member
        for member in members
        if PurePosixPath(member).suffix.lower() in NESTED_ARCHIVE_SUFFIXES
    )
