"""Notice archives the browser saves, for sites without a mod-manager link.

AyakaMods has no protocol handler like Nexus' nxm://, so the browser saves the
file itself. A watch remembers what the folder held when it started and
reports new archives once the browser has finished writing them.
"""

from dataclasses import dataclass, field
import errno
from pathlib import Path
import shutil

from omamods.host_programs import CommandRunner

ARCHIVE_SUFFIXES = frozenset({".7z", ".rar", ".zip"})
# Chromium renames '.crdownload' when done; Firefox writes '<name>.part' next
# to an empty '<name>' until the download ends.
PARTIAL_SUFFIXES = frozenset({".crdownload", ".download", ".part", ".tmp"})
CLAIM_SUFFIX = ".claiming"


def downloads_folder(runner: CommandRunner, home: Path) -> Path:
    """Find where browsers save files; e.g. ``downloads_folder(runner, Path.home())``."""
    code, output = runner.run(("xdg-user-dir", "DOWNLOAD"))
    folder = Path(output)
    # Unconfigured, xdg-user-dir answers $HOME, but browsers use ~/Downloads.
    if code or not folder.is_absolute() or folder == home:
        return home / "Downloads"
    return folder


def _is_finished_archive(path: Path) -> bool:
    if path.name.startswith(".") or path.suffix.lower() not in ARCHIVE_SUFFIXES:
        return False
    partials = (path.with_name(path.name + suffix) for suffix in PARTIAL_SUFFIXES)
    return path.is_file() and not any(partial.exists() for partial in partials)


def archive_sizes(folder: Path) -> dict[str, int]:
    """Size every finished archive; e.g. ``archive_sizes(Path('~/Downloads'))``."""
    if not folder.is_dir():
        return {}
    return {
        path.name: path.stat().st_size
        for path in folder.iterdir()
        if _is_finished_archive(path)
    }


@dataclass
class DownloadWatch:
    """New archives in one folder since the watch began; e.g. ``DownloadWatch.start(d)``."""

    folder: Path
    seen: set[str]
    sizes: dict[str, int] = field(default_factory=dict)

    @classmethod
    def start(cls, folder: Path) -> "DownloadWatch":
        """Ignore what is already there; e.g. ``DownloadWatch.start(downloads)``."""
        return cls(folder, set(archive_sizes(folder)))

    def poll(self) -> tuple[Path, ...]:
        """Report archives whose size held since the last poll; e.g. ``watch.poll()``."""
        current = {
            name: size
            for name, size in archive_sizes(self.folder).items()
            if name not in self.seen
        }
        settled = sorted(
            name
            for name, size in current.items()
            if size > 0 and self.sizes.get(name) == size
        )
        self.seen.update(settled)
        self.sizes = {n: s for n, s in current.items() if n not in self.seen}
        return tuple(self.folder / name for name in settled)


def _copy_across(source: Path, target: Path) -> None:
    # Never leave a half copy staged, and never delete the source before the
    # copy is complete under its final name.
    partial = target.with_name(f".{target.name}{CLAIM_SUFFIX}")
    try:
        shutil.copyfile(source, partial)
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    source.unlink()


def claim_download(source: Path, destination: Path) -> Path:
    """Move an arrival into staging; e.g. ``claim_download(zip_path, file_folder)``."""
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / source.name
    if target.exists():
        raise ValueError(f"staged file={str(target)!r}: expected no file there yet")
    try:
        source.rename(target)
    except OSError as failure:
        if failure.errno != errno.EXDEV:
            raise
        _copy_across(source, target)  # Downloads is on another filesystem.
    return target
