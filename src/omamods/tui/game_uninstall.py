"""Uninstall every mod of one game for the TUI, across Nexus, Ayaka, and releases."""

from typing import TYPE_CHECKING

from omamods.game_revert import GameRevert, OwnedRecord, revert_game_records
from omamods.install_records import mod_state_records
from omamods.pak_games import PakOverlayGame
from omamods.staging import StagedMod

if TYPE_CHECKING:
    from omamods.tui.service import ModsService


class GameUninstall:
    """Revert a whole game; e.g. ``service.game_uninstall.revert_mods(sb, mods)``."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service

    def installed_mods(self, game: PakOverlayGame) -> tuple[StagedMod, ...]:
        """List mods with an installed file; e.g. ``uninstall.installed_mods(sb)``."""
        return tuple(mod for mod in self.service.staged_mods(game) if mod.installed)

    def owned_records(
        self, game: PakOverlayGame, mods: tuple[StagedMod, ...]
    ) -> tuple[OwnedRecord, ...]:
        """Find the mods' install records; e.g. ``uninstall.owned_records(sb, mods)``."""
        return tuple(
            OwnedRecord(mod.site, mod.mod_id, record)
            for mod in mods
            for record in mod_state_records(
                self.service.state_root(mod.site), game, mod.mod_id
            )
        )

    def revert_mods(
        self, game: PakOverlayGame, mods: tuple[StagedMod, ...]
    ) -> GameRevert:
        """Revert the mods' files, past failures; e.g. ``uninstall.revert_mods(sb, mods)``."""
        return revert_game_records(game, self.owned_records(game, mods))
