"""What x does on the mods screen: remove a whole mod, or one download.

On the mod list x removes the highlighted mod: every download it has and its
page details, so it leaves the list (a adds it again). On the files table x
deletes just that file's download. x used to act on the file under the
files-table cursor even from the mod list, so a mod whose highlighted file was
never downloaded could not be removed at all. Kept out of mods_screen.py,
which is at its size limit.
"""

from collections.abc import Callable
from pathlib import Path

from textual.app import App
from textual.widget import Widget

from omamods.nexus_api import NexusFile, describe_nexus_file
from omamods.pak_games import PakOverlayGame
from omamods.staging import StagedMod
from omamods.tui.context_hints import LISTED_SITES
from omamods.tui.dialogs import ConfirmDialog
from omamods.tui.service import ModsService


def removes_whole_mod(focused: Widget | None, mod: StagedMod) -> bool:
    """x on the mod list removes the mod; e.g. ``removes_whole_mod(w, staged)``."""
    on_list = focused is not None and focused.id == "mods"
    return on_list and mod.site in LISTED_SITES


def describe_mod_removal(mod: StagedMod) -> str:
    """Say what x deletes; e.g. ``describe_mod_removal(staged)``."""
    names = [path.name for path in mod.archives.values()]
    if not names:
        return "Nothing is downloaded. Its page details are dropped; a adds it again."
    listed = "\n".join(f"  {name}" for name in names)
    return f"Deletes these downloads:\n{listed}\nThe game is not touched."


class RemoveDownloadActions:
    """Mixin for ModsScreen; e.g. ``screen.action_remove_staged()``."""

    # Annotations only: method stubs here would shadow Screen.notify in the MRO.
    app: App[None]
    current: StagedMod | None
    game: PakOverlayGame
    service: ModsService
    notify: Callable[..., None]
    reload: Callable[[], None]
    _attempt: Callable[[Callable[[], object]], object | None]
    _selected_file: Callable[[], NexusFile | None]

    def action_remove_staged(self) -> None:
        """x: remove the mod from the list, or a file's download."""
        mod = self.current
        if mod is not None and removes_whole_mod(self.app.focused, mod):
            self.confirm_remove_mod(mod)
            return
        file = self._selected_file()
        if file is not None and mod is not None:
            self.confirm_remove(file)

    def confirm_remove_mod(self, mod: StagedMod) -> None:
        """Ask, then delete a mod's downloads; e.g. ``screen.confirm_remove_mod(m)``."""
        if mod.installed:
            self.notify(f"{mod.title} is installed: u uninstalls it first.")
            return
        dialog = ConfirmDialog(
            f"Remove {mod.title} from the list?", describe_mod_removal(mod)
        )
        self.app.push_screen(dialog, lambda yes: yes and self._remove_mod(mod))

    def _remove_mod(self, mod: StagedMod) -> None:
        remove = self.service.remove_mod
        if self._attempt(lambda: remove(self.game, mod.mod_id, mod.site)):
            self.notify(f"Removed {mod.title}")
        self.reload()

    def confirm_remove(self, file: NexusFile) -> None:
        """Ask, then delete a download; for example, ``screen.confirm_remove(file)``."""
        if self.current is None or file.file_id not in self.current.archives:
            self.notify(f"Nothing to remove: {file.file_name} is not downloaded.")
            return
        mod = self.current
        dialog = ConfirmDialog(
            f"Delete the download {file.file_name}?",
            f"{describe_nexus_file(file)}\nThe game is not touched.",
        )
        self.app.push_screen(dialog, lambda yes: yes and self._remove(mod, file))

    def _remove(self, mod: StagedMod, file: NexusFile) -> None:
        removed = self._attempt(
            lambda: self.service.remove_staged(
                self.game, mod.mod_id, file.file_id, mod.site
            )
        )
        if isinstance(removed, Path):
            self.notify(f"Deleted {removed.name}")
        self.reload()
