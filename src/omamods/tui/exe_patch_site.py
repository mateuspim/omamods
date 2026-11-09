"""Executable patches for the TUI: report, apply, and revert one game's patch.

Games such as METAL GEAR RISING have no mods to download; their fix is a
built-in patch of the game's own exe (see exe_patch_games). The games screen
calls these through the service so screens never touch game files.
"""

from typing import TYPE_CHECKING

from omamods.exe_patch_games import ExePatchGame
from omamods.exe_patch_install import (
    ExePatchTarget,
    apply_exe_patch,
    describe_patch_state,
    load_patch_record,
    revert_exe_patch,
)
from omamods.game_shelf import ShelfEntry

if TYPE_CHECKING:
    from omamods.tui.service import ModsService


class ExePatchSite:
    """Patch actions behind the service; e.g. ``service.exe_patch.apply(e, '3440x1440')``."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service

    def _game(self, entry: ShelfEntry) -> ExePatchGame:
        if entry.exe_patch is None:
            raise ValueError(f"{entry.name}: expected a game with a built-in exe patch")
        return entry.exe_patch

    def target(self, entry: ShelfEntry) -> ExePatchTarget:
        """Locate the exe and its records; e.g. ``service.exe_patch.target(mgr)``."""
        game, install = self._game(entry), entry.install
        exe = install.install_path / game.exe_name if install else None
        if exe is None or not exe.is_file():
            raise ValueError(f"{entry.name}: expected an installed {game.exe_name}")
        root = self.service.settings.storage_root
        return ExePatchTarget.for_game(root, game.game_id, exe)

    def is_patched(self, entry: ShelfEntry) -> bool:
        """Tell whether a patch record exists; e.g. ``site.is_patched(mgr)``."""
        return load_patch_record(self.target(entry)) is not None

    def state(self, entry: ShelfEntry) -> str:
        """Describe the exe; e.g. ``service.exe_patch.state(mgr)``."""
        return describe_patch_state(self.target(entry))

    def apply(self, entry: ShelfEntry, option: str) -> str:
        """Back up and patch; e.g. ``service.exe_patch.apply(mgr, '3440x1440')``."""
        game, target = self._game(entry), self.target(entry)
        original = target.exe.read_bytes()
        patched = game.build(original, option)
        apply_exe_patch(target, original, patched, game.describe(option))
        return f"{entry.name}: patched for {option}; original kept in storage"

    def revert(self, entry: ShelfEntry) -> str:
        """Restore the original; e.g. ``service.exe_patch.revert(mgr)``."""
        return revert_exe_patch(self.target(entry))
