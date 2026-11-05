"""Remove folders a clean-up emptied, without touching the game's own."""

from collections.abc import Iterable
from pathlib import Path


def _removable(folder: Path, stop: Path, protect: frozenset[Path]) -> bool:
    if folder == stop or folder in protect or not folder.is_relative_to(stop):
        return False
    return folder.is_dir() and not any(folder.iterdir())


def prune_empty_parents(
    files: Iterable[Path], stop: Path, protect: frozenset[Path] = frozenset()
) -> int:
    """Remove emptied folders up to ``stop``; e.g. ``prune_empty_parents(moved, game_root)``.

    ``stop`` and ``protect`` themselves always stay, even when empty.
    """
    removed = 0
    for file in sorted(files, key=lambda path: len(path.parts), reverse=True):
        folder = file.parent
        while _removable(folder, stop, protect):
            folder.rmdir()
            removed += 1
            folder = folder.parent
    return removed
