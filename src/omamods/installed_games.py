"""Installed games from any launcher, in the one shape the TUI lists."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InstalledGame:
    """One launcher's record of a game on disk; launcher metadata, not verification."""

    store: str
    app_id: str
    name: str
    install_path: Path
    ready: bool
    size_bytes: int | None = None
    library: Path | None = None
    build_id: str | None = None
    proton_prefix: Path | None = None


@dataclass(frozen=True)
class InstalledScan:
    """Games found by one or more launchers, plus records that could not be read."""

    games: tuple[InstalledGame, ...]
    warnings: tuple[str, ...]


def combine_scans(*scans: InstalledScan) -> InstalledScan:
    """Merge launcher results; e.g. ``combine_scans(steam_scan, heroic_scan)``."""
    return InstalledScan(
        tuple(game for scan in scans for game in scan.games),
        tuple(warning for scan in scans for warning in scan.warnings),
    )
