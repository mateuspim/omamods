"""AyakaMods actions for a game's mods screen.

Split from mods_screen.py, which is near the 500-line limit. AyakaMods has no
mod-manager download link, so adding a mod opens its page in the browser and
the screen takes the file once the browser has saved it.
"""

from textual import work

from omamods.staging import StagedMod
from omamods.tui.requirement_actions import RequirementScreen


class AyakaScreen(RequirementScreen):
    """Base for ModsScreen: add AyakaMods mods and pick up their downloads."""

    def reload(self) -> None:
        """Re-read staging; ModsScreen provides it."""
        raise NotImplementedError(f"screen={self!r}: expected reload")

    def fetch_ayaka(self, url: str) -> None:
        """Stage a page and open it to download; e.g. ``screen.fetch_ayaka(url)``."""
        self.notify("Fetching mod details from AyakaMods...")
        self._ayaka_worker(url)

    @work(thread=True)
    def _ayaka_worker(self, url: str) -> None:
        mod = self._attempt(lambda: self.service.ayaka.add(self.game, url))
        if mod is None:
            return
        self.app.call_from_thread(self.reload)
        self.watch_ayaka(mod)

    def watch_ayaka(self, mod: StagedMod) -> None:
        """Open the mod page and wait for a file; e.g. ``screen.watch_ayaka(mod)``."""
        message = self._attempt(lambda: self.service.ayaka.watch(self.game, mod))
        if message is not None:
            self.notify(message, timeout=20)

    def cancel_ayaka(self) -> None:
        """Stop waiting for a download; e.g. ``screen.cancel_ayaka()``."""
        message = self._attempt(self.service.ayaka.cancel)
        if message is not None:
            self.notify(message)

    def take_ayaka_arrivals(self) -> None:
        """Stage files the browser finished; runs on a timer."""
        messages = self._attempt(self.service.ayaka.take_arrivals)
        if not messages:
            return
        for message in messages:
            self.notify(message, timeout=15)
        self.reload()
