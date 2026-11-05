"""Host paths and I/O adapters the TUI service is built from.

Split from service.py, which passed the 500-line limit.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from omamods.ayaka_download import AyakaSession
from omamods.ayaka_pages import AyakaPageTransport
from omamods.byte_ranges import FileRanges
from omamods.cdn_download import RetryPolicy
from omamods.game_shelf import ShelfScanner
from omamods.host_programs import CommandRunner, Launcher
from omamods.installed_containers import OpenRanges
from omamods.nexus_api import NexusTransport
from omamods.nexus_config import ConfigFiles, UserSettings
from omamods.omarchy_palette import PaletteReader
from omamods.pak_archive import ArchiveReader
from omamods.pak_games import PakOverlayGame
from omamods.release_api import ReleaseTransport
from omamods.steam_process import SteamProcess

PaksLocator = Callable[[PakOverlayGame, UserSettings], Path]
# Maps a Steam app ID to every local user's launch options for it.
LaunchOptionsReader = Callable[[str], tuple[str, ...]]
# Writes (app ID, line) into Steam's configs, backing them up into a folder.
LaunchOptionsWriter = Callable[[str, str, Path], tuple[Path, ...]]


def no_launch_options(app_id: str) -> tuple[str, ...]:
    """Stand in when Steam is not searched; e.g. ``no_launch_options('1091500')``."""
    return ()


@dataclass(frozen=True)
class TuiHost:
    """Host paths and I/O adapters the TUI needs."""

    config_path: Path
    fallback_root: Path
    environment: Mapping[str, str]
    config_files: ConfigFiles
    transport: NexusTransport
    reader: ArchiveReader
    runner: CommandRunner
    launcher: Launcher
    locate_paks: PaksLocator
    executable: Path
    applications: Path
    scan_shelf: ShelfScanner
    browser: str | None = None
    retry: RetryPolicy = RetryPolicy()
    read_launch_options: LaunchOptionsReader = no_launch_options
    ayaka_pages: AyakaPageTransport | None = None
    # Opens a logged-in session from the saved xf_user cookie.
    ayaka_session: Callable[[str], AyakaSession] | None = None
    # Where the browser saves files, watched for AyakaMods downloads.
    downloads: Path | None = None
    palette_reader: PaletteReader | None = None
    # Reads Codeberg/GitHub releases anonymously (MGSVFix).
    release_transport: ReleaseTransport | None = None
    write_launch_options: LaunchOptionsWriter | None = None
    steam: SteamProcess | None = None
    # Reads pak and utoc indexes for asset collision checks.
    open_ranges: OpenRanges = FileRanges
