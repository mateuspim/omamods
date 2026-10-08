"""Wait for the one AyakaMods download the browser is fetching.

Arrivals are matched to a mod only by timing, so a single wait at a time keeps
two mods' downloads from being swapped.
"""

from dataclasses import dataclass
from pathlib import Path

from omamods.download_watch import DownloadWatch


@dataclass
class AyakaWait:
    """A mod whose download is expected in ``watch.folder``."""

    game_id: str
    mod_id: int
    watch: DownloadWatch


class AyakaWaits:
    """Hold at most one wait; e.g. ``AyakaWaits(Path('~/Downloads'))``."""

    def __init__(self, downloads: Path) -> None:
        self.downloads = downloads
        self.current: AyakaWait | None = None

    def start(self, game_id: str, mod_id: int) -> AyakaWait | None:
        """Watch for a mod's file; returns the wait it replaced. E.g. ``waits.start('co', 1)``."""
        replaced = self.current
        self.current = AyakaWait(game_id, mod_id, DownloadWatch.start(self.downloads))
        return replaced

    def cancel(self) -> AyakaWait | None:
        """Stop waiting; e.g. ``waits.cancel()``."""
        stopped, self.current = self.current, None
        return stopped

    def arrivals(self) -> tuple[AyakaWait, tuple[Path, ...]] | None:
        """Report finished downloads and stop waiting; e.g. ``waits.arrivals()``."""
        wait = self.current
        if wait is None:
            return None
        arrived = wait.watch.poll()
        if not arrived:
            return None
        self.current = None
        return wait, arrived
