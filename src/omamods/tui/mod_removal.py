"""What x does on the mods screen: delete a download, or drop an empty mod.

x deletes the highlighted download. A mod whose page was fetched but whose
files never were has no download to delete, so x used to say so and leave the
mod listed; now it offers to drop the mod instead. Kept out of mods_screen.py,
which is at its size limit.
"""

from collections.abc import Callable
from pathlib import Path

from textual.app import App

from omamods.nexus_api import NexusFile, describe_nexus_file
from omamods.pak_games import PakOverlayGame
from omamods.staging import StagedMod
from omamods.tui.context_hints import LISTED_SITES
from omamods.tui.dialogs import ConfirmDialog
from omamods.tui.service import ModsService


def can_forget(mod: StagedMod) -> bool:
    """Nothing downloaded or installed; e.g. ``can_forget(fetched_page_only)``."""
    return mod.site in LISTED_SITES and not mod.archives and not mod.installed


class RemoveDownloadActions:
    """Mixin for ModsScreen; e.g. ``screen.confirm_remove(file)``."""

    # Annotations only: method stubs here would shadow Screen.notify in the MRO.
    app: App[None]
    current: StagedMod | None
    game: PakOverlayGame
    service: ModsService
    notify: Callable[..., None]
    reload: Callable[[], None]
    _attempt: Callable[[Callable[[], object]], object | None]

    def confirm_remove(self, file: NexusFile) -> None:
        """Ask, then delete a download; for example, ``screen.confirm_remove(file)``."""
        if self.current is None or file.file_id not in self.current.archives:
            self.remove_without_download(file)
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

    def remove_without_download(self, file: NexusFile) -> None:
        """x on a file that is not downloaded; e.g. ``screen.remove_without_download(f)``."""
        mod = self.current
        if mod is None or not can_forget(mod):
            self.notify(f"Nothing to remove: {file.file_name} is not downloaded.")
            return
        dialog = ConfirmDialog(
            f"Remove {mod.title} from the list?",
            "Nothing from it is downloaded or installed. a adds it again.",
        )
        self.app.push_screen(dialog, lambda yes: yes and self._forget(mod))

    def _forget(self, mod: StagedMod) -> None:
        forget = self.service.forget_mod
        if self._attempt(lambda: forget(self.game, mod.mod_id, mod.site)):
            self.notify(f"Removed {mod.title} from the list")
        self.reload()
