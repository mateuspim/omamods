"""Built-in executable patches as mods: list, apply, and restore them.

Games such as METAL GEAR RISING have a fix that is a patch of the game's own
exe (see exe_patch_games). It is listed first in the game's mods like any
other mod, so i installs it and u restores the original. x also deletes the stored
backup and takes the patch off the list until a adds it back. Nothing is
downloaded and no archive is staged.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from omamods.display_sizes import (
    Monitor,
    SizeChoice,
    read_monitors,
    resolution_choices,
)
from omamods.exe_patch_games import EXE_PATCH_GAMES, ExePatchGame
from omamods.exe_patch_install import (
    ExePatchTarget,
    apply_exe_patch,
    describe_patch_state,
    ensure_unpatched,
    load_patch_record,
    remove_patch_files,
    revert_exe_patch,
)
from omamods.mod_sites import PATCH_SITE
from omamods.nexus_api import NexusFile, NexusModInfo
from omamods.pak_games import PakOverlayGame
from omamods.staging import StagedMod

if TYPE_CHECKING:
    from omamods.tui.service import ModsService

PATCH_MOD_ID = PATCH_FILE_ID = 1
PAGE_URL = "https://github.com/mateuspim/omamods/blob/master/games/{game}/README.md"


class ExePatchSite:
    """Patch actions behind the service; e.g. ``service.exe_patch.apply(mgr, '3440x1440')``."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service

    def _patch(self, game: PakOverlayGame) -> ExePatchGame:
        patch = EXE_PATCH_GAMES.get(game.game_id)
        if patch is None:
            raise ValueError(f"{game.name}: expected a game with a built-in exe patch")
        return patch

    def target(self, game: PakOverlayGame) -> ExePatchTarget:
        """Locate the exe and its records; e.g. ``service.exe_patch.target(mgr)``."""
        settings = self.service.settings
        exe = self.service.host.locate_paks(game, settings) / self._patch(game).exe_name
        if not exe.is_file():
            raise ValueError(f"{game.name}: expected an installed {exe.name}")
        return ExePatchTarget.for_game(settings.storage_root, game.game_id, exe)

    def state(self, game: PakOverlayGame) -> str:
        """Describe the exe; e.g. ``service.exe_patch.state(mgr)``."""
        return describe_patch_state(self.target(game))

    def _installed(self, game: PakOverlayGame) -> frozenset[int]:
        try:
            patched = load_patch_record(self.target(game)) is not None
        except (OSError, ValueError):
            return frozenset()  # Not installed: listed, and i explains why.
        return frozenset({PATCH_FILE_ID}) if patched else frozenset()

    def _placeholder(self, game: PakOverlayGame) -> Path:
        # Marks the file as ready to install; never created, so removing a
        # "download" can never reach the game's exe.
        root = self.service.settings.storage_root
        return root / "state" / game.game_id / "exe-patch.builtin"

    def staged_mod(self, game: PakOverlayGame, mod_id: int = PATCH_MOD_ID) -> StagedMod:
        """Describe the patch as a mod; e.g. ``service.exe_patch.staged_mod(mgr)``."""
        patch = self._patch(game)
        info = NexusModInfo(patch.mod_title, patch.summary, "OmaMods", "", None)
        file = NexusFile(
            PATCH_FILE_ID, patch.exe_name, "MAIN", 0, "Ultrawide exe patch"
        )
        archives = {PATCH_FILE_ID: self._placeholder(game)}
        installed = self._installed(game)
        return StagedMod(mod_id, info, (file,), archives, None, installed, PATCH_SITE)

    def _removed_marker(self, game: PakOverlayGame) -> Path:
        root = self.service.settings.storage_root
        return root / "state" / game.game_id / "exe-patch.removed"

    def staged_mods(self, game: PakOverlayGame) -> tuple[StagedMod, ...]:
        """List the game's patch unless x removed it; e.g. ``site.staged_mods(mgr)``."""
        if game.game_id not in EXE_PATCH_GAMES:
            return ()
        return () if self._removed_marker(game).exists() else (self.staged_mod(game),)

    def list_again(self, game: PakOverlayGame) -> bool:
        """Undo x's unlisting; e.g. ``site.list_again(mgr)`` is True if it was off."""
        marker = self._removed_marker(game)
        if not marker.exists():
            return False
        marker.unlink()
        if not any(marker.parent.iterdir()):
            marker.parent.rmdir()
        return True

    def monitors(self) -> tuple[Monitor, ...]:
        """Read the connected monitors, or none; e.g. ``site.monitors()``."""
        return read_monitors(self.service.host.runner)

    def resolution_choices(
        self, monitors: tuple[Monitor, ...]
    ) -> tuple[SizeChoice, ...]:
        """Monitors first, then common sizes; e.g. ``site.resolution_choices(mine)``."""
        return resolution_choices(monitors)

    def page_url(self, game: PakOverlayGame) -> str:
        """Link the adapter README; e.g. ``service.exe_patch.page_url(mgr)``."""
        return PAGE_URL.format(game=game.game_id)

    def apply(self, game: PakOverlayGame, option: str) -> str:
        """Back up and patch; e.g. ``service.exe_patch.apply(mgr, '3440x1440')``."""
        patch, target = self._patch(game), self.target(game)
        ensure_unpatched(target)
        original = target.exe.read_bytes()
        patched = patch.build(original, option)
        apply_exe_patch(target, original, patched, patch.describe(option))
        return f"{game.name}: patched for {option}; original kept in storage"

    def revert(self, game: PakOverlayGame) -> str:
        """Restore the original; e.g. ``service.exe_patch.revert(mgr)``."""
        return revert_exe_patch(self.target(game))

    def remove(self, game: PakOverlayGame) -> str:
        """Restore if patched, delete stored files, unlist; e.g. ``site.remove(mgr)``."""
        message = remove_patch_files(self.target(game))
        marker = self._removed_marker(game)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return f"{message}; a lists the patch again"

    def after_apply(self, game: PakOverlayGame) -> str:
        """What to do in the game next; e.g. ``site.after_apply(mgr)``."""
        return self._patch(game).after_apply
