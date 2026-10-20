"""Mods screen actions that rename an installed file so it loads last (P)."""

import asyncio

from textual import work
from textual.binding import Binding

from omamods.nexus_api import NexusFile
from omamods.staging import StagedMod
from omamods.tui.dialogs import ConfirmDialog
from omamods.tui.load_order_choices import ContainerRename
from omamods.tui.mod_detail import ModDetail
from omamods.tui.requirement_actions import RequirementScreen

ENGINE_NOTE = (
    "Unreal mounts mods by file name: a _<n>_P number loads over plain _P mods."
)


class LoadOrderScreen(RequirementScreen):
    """Mix into ModsScreen; e.g. ``class ModsScreen(..., LoadOrderScreen)``."""

    BINDINGS = [Binding("P", "load_last", "Load file last", show=False)]
    current: StagedMod | None = None

    def _selected_file(self) -> NexusFile | None:
        """The highlighted file; ModsScreen provides it."""
        raise NotImplementedError(f"screen={self!r}: expected _selected_file")

    def _installed_selection(self) -> tuple[StagedMod, NexusFile] | None:
        file = self._selected_file()
        if file is None or self.current is None:
            return None
        if file.file_id not in self.current.installed:
            self.notify(f"{file.file_name}: install it first, then press P.")
            return None
        return self.current, file

    def action_load_last(self) -> None:
        """Make the highlighted file win its clashes; e.g. ``screen.action_load_last()``."""
        selection = self._installed_selection()
        if selection is not None:
            self.confirm_load_order(*selection, restore=False)

    def action_load_default(self) -> None:
        """Give the file back its archive names; e.g. ``screen.action_load_default()``."""
        selection = self._installed_selection()
        if selection is not None:
            self.confirm_load_order(*selection, restore=True)

    def _renames(
        self, mod: StagedMod, file: NexusFile, restore: bool
    ) -> tuple[tuple[ContainerRename, ...], str]:
        choices = self.service.load_order
        find = choices.to_default if restore else choices.to_load_last
        renames = find(self.game, mod, file.file_id)
        return renames, choices.describe(self.game, renames)

    @work
    async def confirm_load_order(
        self, mod: StagedMod, file: NexusFile, restore: bool
    ) -> None:
        """Ask, then rename; e.g. ``screen.confirm_load_order(mod, file, False)``."""
        found = await asyncio.to_thread(
            self._attempt, lambda: self._renames(mod, file, restore)
        )
        if found is None:
            return
        renames, details = found
        if not renames:
            self.notify(self._nothing_to_do(file, restore))
            return
        verb = "Restore the original names of" if restore else "Load last:"
        dialog = ConfirmDialog(f"{verb} {file.file_name}?", f"{details}\n{ENGINE_NOTE}")
        if await self.app.push_screen_wait(dialog):
            await asyncio.to_thread(self._apply_renames, mod, file, renames)

    def _nothing_to_do(self, file: NexusFile, restore: bool) -> str:
        if restore:
            return f"{file.file_name}: already installed under its original names."
        return f"{file.file_name}: already loads over every mod it collides with."

    def _apply_renames(
        self, mod: StagedMod, file: NexusFile, renames: tuple[ContainerRename, ...]
    ) -> None:
        moved = self._attempt(lambda: self.service.load_order.apply(self.game, renames))
        if moved is None:
            return
        self.notify(f"Renamed {moved} files of {file.file_name}")
        # The install state is unchanged, so reload() would not re-check clashes.
        self.app.call_from_thread(self.query_one(ModDetail).show_mod, mod)
