"""Save a game's launch options into Steam for the TUI, closing Steam if needed.

Steam would overwrite the edit on exit, so a running client is shut down
first and started again afterwards; the screen asks before that happens.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from omamods.steam_launch_writer import backup_folder
from omamods.steam_process import SteamProcess

if TYPE_CHECKING:
    from omamods.tui.service import ModsService


class SteamSetup:
    """Write launch options; e.g. ``service.steam_setup.save('287700', line)``."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service

    def _steam(self) -> SteamProcess:
        steam = self.service.host.steam
        if steam is None:
            raise ValueError("Steam client: expected a SteamProcess in TuiHost")
        return steam

    def steam_running(self) -> bool:
        """Report whether saving must close Steam; e.g. ``setup.steam_running()``."""
        return self._steam().running()

    def save(self, app_id: str, line: str) -> str:
        """Close Steam if open, write, restart it; e.g. ``setup.save('287700', line)``."""
        writer = self.service.host.write_launch_options
        if writer is None:
            raise ValueError("launch options: expected a writer in TuiHost")
        steam = self._steam()
        was_running = steam.running()
        if was_running:
            steam.shut_down()
        backups = backup_folder(self.service.settings.storage_root, datetime.now())
        try:
            written = writer(app_id, line, backups)
        finally:
            if was_running:
                steam.start()  # Even after a failed write, give Steam back.
        users = "user" if len(written) == 1 else "users"
        return (
            f"Saved to Steam for {len(written)} {users}: {line} (backup in {backups})"
        )
