"""Uninstall every mod of a game from its mods screen (U, :uninstall-all).

Split from mods_screen.py, which is near the 500-line limit.
"""

from collections.abc import Mapping

from textual import work

from omamods.game_revert import GameRevert, RecordRevert
from omamods.staging import StagedMod
from omamods.tui.dialogs import ConfirmDialog
from omamods.tui.requirement_actions import ERROR_TOAST_SECONDS, RequirementScreen

ModTitles = Mapping[tuple[str, int], str]


def describe_installed(mods: tuple[StagedMod, ...]) -> str:
    """List mods and their installed files; e.g. ``describe_installed(mods)``."""
    lines = [f"  {mod.title}: {len(mod.installed)} file(s)" for mod in mods]
    total = sum(len(mod.installed) for mod in mods)
    lines.append(f"Total: {total} installed file(s) in {len(mods)} mod(s)")
    return "\n".join(lines)


def _failure_line(failure: RecordRevert, titles: ModTitles) -> str:
    title = titles.get((failure.site, failure.mod_id), f"mod {failure.mod_id}")
    file = "" if failure.file_id is None else f" file {failure.file_id}"
    return f"{title}{file}: {failure.error}"


def summarize_revert(outcome: GameRevert, titles: ModTitles) -> str:
    """Say what uninstalling all did; e.g. ``summarize_revert(outcome, titles)``."""
    mods = len(outcome.cleared_mods())
    summary = f"Removed {outcome.removed_files()} files from {mods} mods"
    failures = outcome.failures()
    if not failures:
        return summary
    lines = "\n".join(_failure_line(failure, titles) for failure in failures)
    return f"{summary}; {len(failures)} failed:\n{lines}"


class UninstallAllScreen(RequirementScreen):
    """Base for ModsScreen: revert every installed file of the game at once."""

    def reload(self) -> None:
        """Re-read staging; ModsScreen provides it."""
        raise NotImplementedError(f"screen={self!r}: expected reload")

    def action_uninstall_all(self) -> None:
        """Ask, then uninstall every mod; e.g. ``screen.action_uninstall_all()``."""
        uninstall = self.service.game_uninstall
        mods = self._attempt(lambda: uninstall.installed_mods(self.game))
        if mods is None:
            return
        if not mods:
            self.notify(f"Nothing is installed for {self.game.name}.")
            return
        title = f"Uninstall all {len(mods)} mod(s) of {self.game.name}?"
        dialog = ConfirmDialog(title, describe_installed(mods))
        self.app.push_screen(dialog, lambda yes: yes and self._revert_all(mods))

    @work(thread=True, exclusive=True, group="uninstall-all")
    def _revert_all(self, mods: tuple[StagedMod, ...]) -> None:
        uninstall = self.service.game_uninstall
        outcome = self._attempt(lambda: uninstall.revert_mods(self.game, mods))
        if outcome is not None:
            self._report_revert(outcome, mods)
        self.app.call_from_thread(self.reload)

    def _report_revert(self, outcome: GameRevert, mods: tuple[StagedMod, ...]) -> None:
        titles = {(mod.site, mod.mod_id): mod.title for mod in mods}
        message = summarize_revert(outcome, titles)
        if not outcome.failures():
            self.notify(message)
            return
        self.notify(message, severity="warning", timeout=ERROR_TOAST_SECONDS)
