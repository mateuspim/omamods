"""Requirement checks and Steam launch options for a game's mods screen.

Split from mods_screen.py, which had reached the 500-line limit.
"""

import asyncio
from collections.abc import Callable
from typing import TypeVar

from textual import work
from textual.screen import Screen

from omamods.nexus_api import NexusFile
from omamods.pak_games import PakOverlayGame
from omamods.mod_sites import NEXUS_SITE
from omamods.staging import StagedMod
from omamods.tui.launch_options_dialog import LaunchOptionsDialog
from omamods.tui.requirements_dialog import RequirementsDialog
from omamods.tui.service import ModsService

Result = TypeVar("Result")
LAUNCH_WARNING = (
    "Steam or the Proton prefix is missing what RED4ext/CET need; "
    "press L to see the fix and copy it."
)


class RequirementScreen(Screen[None]):
    """Base for ModsScreen: installs that check requirements first."""

    service: ModsService
    game: PakOverlayGame
    # Set from the first i until its dialog closes, so repeats are ignored.
    checking_requirements: bool = False

    def install_now(self, mod: StagedMod, files: tuple[NexusFile, ...]) -> None:
        """Install without a requirement check; ModsScreen provides it."""
        raise NotImplementedError(f"screen={self!r}: expected install_now")

    def _attempt(self, action: Callable[[], Result]) -> Result | None:
        try:
            return action()
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)
            return None

    def install_files(self, mod: StagedMod, files: tuple[NexusFile, ...]) -> None:
        """Install staged files; e.g. ``screen.install_files(mod, (file,))``.

        Every path (i, Enter, :install) checks Cyberpunk requirements first:
        Enter on a staged mod used to install it with its requirements missing.
        """
        # Requirements are looked up on Nexus by mod ID, which Ayaka mods lack.
        nexus = mod.site == NEXUS_SITE
        if self.game.redengine and nexus and self.service.has_api_key():
            self._check_requirements(mod, files)
            return
        self.install_now(mod, files)

    def _check_requirements(self, mod: StagedMod, files: tuple[NexusFile, ...]) -> None:
        target = self.service.requirements.target_name
        if target is not None:
            self.notify(
                f"Already installing {target} and its requirements; D shows downloads."
            )
            return
        if self.checking_requirements:
            self.notify("Already checking requirements; wait for the dialog.")
            return
        self.checking_requirements = True
        self.notify("Checking the mod's requirements on Nexus...")
        self.install_with_requirements(mod, files)

    @work
    async def install_with_requirements(
        self, mod: StagedMod, files: tuple[NexusFile, ...]
    ) -> None:
        try:
            await self._confirm_requirements(mod, files)
        finally:
            self.checking_requirements = False

    async def _confirm_requirements(
        self, mod: StagedMod, files: tuple[NexusFile, ...]
    ) -> None:
        flow = self.service.requirements
        plan = await asyncio.to_thread(
            self._attempt, lambda: flow.plan(self.game, mod, files)
        )
        if plan is None:
            return
        if not plan.needs_work:
            if plan.launch_advice is not None and plan.launch_advice.needed:
                self.notify(LAUNCH_WARNING, severity="warning", timeout=20)
            self.install_now(mod, files)
            return
        if not await self.app.push_screen_wait(
            RequirementsDialog(plan, self.service.copy_to_clipboard)
        ):
            return
        if self._attempt(lambda: flow.start(plan)) is None:
            return
        self.notify("Installing requirements in order; D shows downloads.", timeout=10)

    @work(thread=True)
    def _warn_launch_options(self) -> None:
        flow = self.service.requirements
        advice = self._attempt(lambda: flow.launch_advice(self.game))
        if advice is not None and advice.needed:
            self.notify(LAUNCH_WARNING, severity="warning", timeout=20)

    def action_launch_options(self) -> None:
        flow = self.service.requirements
        advice = self._attempt(lambda: flow.launch_advice(self.game))
        if advice is None:
            self.notify(f"{self.game.name}: no Steam launch options to check.")
            return
        copier = self.service.copy_to_clipboard
        self.app.push_screen(LaunchOptionsDialog(advice, copier))
