"""The mods screen for games whose fix is a built-in exe patch.

Enter on such a game opens its mods like any other game. The patch is listed
first: i (or Enter on its file) picks a resolution and patches, and u (or Enter
once installed) restores the original exe. Nothing is downloaded, so d and x
explain instead of touching staging. Kept out of mods_screen.py, which is near
its size limit, by overriding the few actions the patch changes.
"""

import asyncio

from textual import work

from omamods.exe_patch_games import EXE_PATCH_GAMES
from omamods.mod_sites import PATCH_SITE
from omamods.nexus_api import NexusFile
from omamods.pak_games import PakOverlayGame
from omamods.staging import StagedMod
from omamods.tui.dialogs import ConfirmDialog, TextPrompt
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.resolution_picker import (
    OTHER_SIZE,
    ResolutionPicker,
    first_allowed,
)
from omamods.tui.service import ModsService

NOTICE_SECONDS = 12
BUILT_IN = "is built in: nothing to download or remove. i patches, u restores."


def mods_screen_for(service: ModsService, game: PakOverlayGame) -> ModsScreen:
    """Open the right mods screen; e.g. ``app.push_screen(mods_screen_for(s, mgr))``."""
    if game.game_id in EXE_PATCH_GAMES:
        return PatchModsScreen(service, game)
    return ModsScreen(service, game)


def _is_patch(mod: StagedMod | None) -> bool:
    return mod is not None and mod.site == PATCH_SITE


class PatchModsScreen(ModsScreen):
    """ModsScreen plus the built-in patch; e.g. ``PatchModsScreen(service, mgr)``."""

    def install_files(self, mod: StagedMod, files: tuple[NexusFile, ...]) -> None:
        if _is_patch(mod):
            self.patch_now(mod)
            return
        super().install_files(mod, files)

    def confirm_uninstall(self, mod: StagedMod, files: tuple[NexusFile, ...]) -> None:
        if not _is_patch(mod):
            super().confirm_uninstall(mod, files)
            return
        details = (
            f"{self._state()}\n\nThe original exe comes back from OmaMods storage."
        )
        dialog = ConfirmDialog(f"Restore {self.game.name}'s original exe?", details)
        self.app.push_screen(dialog, lambda yes: yes and self._restore())

    def action_download(self) -> None:
        if _is_patch(self.current):
            self.notify(f"{self.current.title} {BUILT_IN}")
            return
        super().action_download()

    def action_remove_staged(self) -> None:
        if _is_patch(self.current):
            self.notify(f"{self.current.title} {BUILT_IN}")
            return
        super().action_remove_staged()

    def _state(self) -> str:
        state = self._attempt(lambda: self.service.exe_patch.state(self.game))
        return state or ""

    async def _pick_size(self) -> str | None:
        site = self.service.exe_patch
        monitors = await asyncio.to_thread(site.monitors)
        choices = site.resolution_choices(monitors)
        title = f"{self.game.name}: pick your display resolution"
        picked = await self.app.push_screen_wait(ResolutionPicker(title, choices))
        if picked != OTHER_SIZE:
            return picked
        prompt = TextPrompt(title, "WIDTHxHEIGHT", value=first_allowed(choices))
        return await self.app.push_screen_wait(prompt)

    @work
    async def patch_now(self, mod: StagedMod) -> None:
        size = await self._pick_size()
        if not size:
            return
        details = (
            f"{mod.info.summary if mod.info else ''}\n\nResolution: {size}\n"
            "The original exe is copied to OmaMods storage first."
        )
        if not await self.app.push_screen_wait(
            ConfirmDialog(f"Patch for {size}?", details)
        ):
            return
        site = self.service.exe_patch
        done = await asyncio.to_thread(
            lambda: self._attempt(lambda: site.apply(self.game, size))
        )
        if done:
            self.notify(done, timeout=NOTICE_SECONDS)
            self.notify(site.after_apply(self.game), timeout=NOTICE_SECONDS)
        self.reload()

    @work(thread=True)
    def _restore(self) -> None:
        done = self._attempt(lambda: self.service.exe_patch.revert(self.game))
        if done:
            self.notify(done, timeout=NOTICE_SECONDS)
        self.app.call_from_thread(self.reload)
