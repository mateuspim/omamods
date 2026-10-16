"""Keep a copy of a game file a mod replaces, so uninstalling restores it.

Only prefix config files (a bundle's Engine.ini) replace existing files; every
other install refuses to touch a file it did not create.
"""

from pathlib import Path
import shutil


def originals_folder(record: Path) -> Path:
    """Where one install keeps replaced files; e.g. ``originals_folder(state / '321.config.json')``."""
    return record.with_suffix(".originals")


def set_aside_original(target: Path, saved: Path) -> Path | None:
    """Move an existing file into storage; e.g. ``set_aside_original(ini, saved_ini)``.

    Returns None when there was nothing to keep.
    """
    if not target.is_file():
        return None
    if saved.exists():
        raise ValueError(
            f"saved original={str(saved)!r}: expected none; an earlier install "
            "did not finish its uninstall"
        )
    saved.parent.mkdir(parents=True, exist_ok=True)
    # Copy, then delete: the prefix and storage often sit on different drives.
    shutil.copy2(target, saved)
    target.unlink()
    return saved


def put_back_original(saved: Path, target: Path, folder: Path) -> None:
    """Restore a replaced file; e.g. ``put_back_original(saved_ini, ini, originals)``."""
    if saved.is_file():
        target.unlink(missing_ok=True)
        shutil.copy2(saved, target)
        saved.unlink()
    # A missing copy was deleted by hand; the game writes a fresh file on launch.
    _remove_empty_folders(saved.parent, folder)


def _remove_empty_folders(start: Path, folder: Path) -> None:
    current = start
    while current.is_relative_to(folder) and current.is_dir():
        if any(current.iterdir()):
            return
        current.rmdir()
        current = current.parent
