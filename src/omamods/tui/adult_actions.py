"""Hide NSFW mods from the mods list and mark mods NSFW by hand."""

from dataclasses import replace

from omamods.adult_marks import AdultMarks, is_adult, with_mark
from omamods.staging import StagedMod
from omamods.tui.ayaka_actions import AyakaScreen
from omamods.tui.mod_rows import mod_key


class AdultScreen(AyakaScreen):
    """Base for ModsScreen: the H toggle and m mark; ModsScreen sets the state."""

    adult = AdultMarks()

    def rebuild_list(self, jump_to_first: bool) -> int:
        """Re-list the mods; ModsScreen provides it."""
        raise NotImplementedError(f"screen={self!r}: expected rebuild_list")

    def load_adult_marks(self) -> None:
        """Read saved NSFW choices; an unreadable file shows everything."""
        self.adult = self._attempt(self.service.adult_marks) or AdultMarks()

    def mod_is_adult(self, mod: StagedMod) -> bool:
        """Apply hand marks over the site's flag; e.g. ``screen.mod_is_adult(mod)``."""
        flagged = mod.info.adult if mod.info else False
        return is_adult(self.adult, self.game.game_id, mod_key(mod), flagged)

    def hidden_mod_keys(self) -> frozenset[str]:
        """Keys the list leaves out; e.g. ``'nexus:12' in screen.hidden_mod_keys()``."""
        if not self.adult.hide:
            return frozenset()
        return frozenset(mod_key(m) for m in self.mods if self.mod_is_adult(m))

    def action_toggle_adult(self) -> None:
        self.set_adult_hidden(not self.adult.hide)

    def set_adult_hidden(self, hide: bool) -> None:
        """Hide or show NSFW mods in every game; e.g. ``screen.set_adult_hidden(True)``."""
        if self._save_adult(replace(self.adult, hide=hide)):
            self.notify("Hiding NSFW mods." if hide else "Showing NSFW mods.")

    def action_mark_adult(self) -> None:
        if self.current is not None:
            self.mark_adult(not self.mod_is_adult(self.current))

    def mark_adult(self, adult: bool) -> None:
        """Mark the selected mod NSFW or not; e.g. ``screen.mark_adult(True)``."""
        mod = self.current
        if mod is None:
            raise ValueError("mod: expected one selected to mark; add one with :add")
        marks = with_mark(self.adult, self.game.game_id, mod_key(mod), adult)
        if not self._save_adult(marks):
            return
        hidden = " and hid it" if adult and marks.hide else ""
        self.notify(f"Marked {mod.title} {'NSFW' if adult else 'not NSFW'}{hidden}.")

    def _save_adult(self, marks: AdultMarks) -> bool:
        if self._attempt(lambda: self.service.save_adult_marks(marks)) is None:
            return False
        self.adult = marks
        self.rebuild_list(jump_to_first=False)
        return True
