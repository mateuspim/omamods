"""Library-wide clean-ups for the TUI: set aside strays (X).

Split from service.py, which passed the 500-line limit.
"""

from pathlib import Path
import time
from typing import TYPE_CHECKING

from omamods.game_shelf import GameShelf
from omamods.mod_sites import AYAKA_SITE, NEXUS_SITE, RELEASE_SITE
from omamods.pak_games import PakOverlayGame
from omamods.untracked_clean import describe_found, set_aside
from omamods.untracked_mods import audit_keyed, shelf_pak_games

if TYPE_CHECKING:
    from omamods.tui.service import ModsService

SITES = (NEXUS_SITE, AYAKA_SITE, RELEASE_SITE)


class LibraryClean:
    """Find and clear mod files across games; e.g. ``service.library_clean.untracked``."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service
        # Mod files found in games with no install record, by shelf key.
        self.untracked: dict[str, tuple[Path, ...]] = {}
        self.game_names: dict[str, str] = {}
        self.pak_games: dict[str, PakOverlayGame] = {}

    def site_roots(self) -> dict[str, Path]:
        """Name each site's storage root; e.g. ``library_clean.site_roots()['nexus']``."""
        return {site: self.service.state_root(site) for site in SITES}

    def audit(self, shelf: GameShelf) -> None:
        """Look for unrecorded mod files in a scan; e.g. ``library_clean.audit(shelf)``."""
        self.pak_games = shelf_pak_games(shelf)
        roots = self.site_roots().values()
        self.untracked = audit_keyed(self.pak_games, roots)
        self.game_names = {entry.key: entry.name for entry in shelf.entries}

    def removed_folder(self) -> Path:
        """Name a new dated folder for moved files; e.g. ``library_clean.removed_folder()``."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return self.service.settings.storage_root / "removed" / stamp

    def clean_untracked(self) -> tuple[int, Path]:
        """Set aside every untracked mod file; e.g. ``count, folder = library_clean.clean_untracked()``."""
        return set_aside(self.untracked, self.removed_folder())

    def untracked_description(self) -> str:
        """Describe what X would move; e.g. ``library_clean.untracked_description()``."""
        return describe_found(self.untracked, self.game_names)
