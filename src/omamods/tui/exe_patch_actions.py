"""Games-screen actions for built-in executable patches.

Split from games_screen.py to keep it focused on the shelf. Enter on a game
with an exe patch asks for the resolution and patches, or offers to restore
the original when the patch is already applied.
"""

from collections.abc import Callable

from textual import work

from omamods.game_shelf import ShelfEntry
from omamods.tui.dialogs import ConfirmDialog, TextPrompt
from omamods.tui.list_search import SearchableScreen
from omamods.tui.service import ModsService

PATCH_SECONDS = 10


class ExePatchScreen(SearchableScreen):
    """Base for GamesScreen: open a game's exe patch instead of its mods."""

    service: ModsService

    def open_exe_patch(self, entry: ShelfEntry) -> None:
        """Ask what to do with the patch; e.g. ``screen.open_exe_patch(mgr)``."""
        site = self.service.exe_patch
        try:
            patched, state = site.is_patched(entry), site.state(entry)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error")
            return
        if patched:
            self._ask_revert(entry, state)
        else:
            self._ask_resolution(entry)

    def _ask_resolution(self, entry: ShelfEntry) -> None:
        help_text = entry.exe_patch.option_help if entry.exe_patch else ""
        prompt = TextPrompt(f"{entry.name}: ultrawide patch", help_text)
        self.app.push_screen(prompt, lambda value: value and self._apply(entry, value))

    def _ask_revert(self, entry: ShelfEntry, state: str) -> None:
        details = f"{state}\n\nThe original exe comes back from OmaMods storage."
        dialog = ConfirmDialog(f"Restore {entry.name}'s original exe?", details)
        self.app.push_screen(dialog, lambda yes: yes and self._revert(entry))

    @work(thread=True)
    def _apply(self, entry: ShelfEntry, option: str) -> None:
        done = self._report(lambda: self.service.exe_patch.apply(entry, option))
        if done and entry.exe_patch is not None:
            self.notify(entry.exe_patch.after_apply, timeout=PATCH_SECONDS)

    @work(thread=True)
    def _revert(self, entry: ShelfEntry) -> None:
        self._report(lambda: self.service.exe_patch.revert(entry))

    def _report(self, action: Callable[[], str]) -> bool:
        try:
            message = action()
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=PATCH_SECONDS)
            return False
        self.notify(message, timeout=PATCH_SECONDS)
        return True
