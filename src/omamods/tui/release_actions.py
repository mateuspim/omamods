"""Repository-release actions for a game's mods screen.

Split from mods_screen.py, which is near the 500-line limit. Release mods
(MGSVFix) are listed before anything is downloaded; d fetches the newest
release and opening the screen says when a newer one than the installed is out.
"""

from textual import work

from omamods.mod_sites import RELEASE_SITE
from omamods.release_sources import sources_for
from omamods.release_staging import pending_update
from omamods.staging import StagedMod
from omamods.tui.requirement_actions import RequirementScreen

UPDATE_SECONDS = 15


class ReleaseScreen(RequirementScreen):
    """Base for ModsScreen: download repository releases and spot updates."""

    def reload(self) -> None:
        """Re-read staging; ModsScreen provides it."""
        raise NotImplementedError(f"screen={self!r}: expected reload")

    def download_release(self, mod: StagedMod) -> None:
        """Fetch the newest release's archive; e.g. ``screen.download_release(mod)``."""
        self.notify(f"{mod.title}: asking for the newest release...")
        self._release_worker(mod)

    @work(thread=True)
    def _release_worker(self, mod: StagedMod) -> None:
        release = self.service.release
        paths = self._attempt(lambda: release.download(self.game, mod.mod_id))
        if paths is None:
            return
        if not paths:
            self.notify(f"{mod.title}: the newest release is already downloaded.")
        for path in paths:
            self.notify(f"{mod.title}: {path.name} downloaded; press i to install")
        self.app.call_from_thread(self.reload)

    def check_release_updates(self) -> None:
        """Look for newer releases of installed mods; runs when the screen opens."""
        if sources_for(self.game.game_id):
            self._updates_worker()

    @work(thread=True)
    def _updates_worker(self) -> None:
        for source in sources_for(self.game.game_id):
            try:
                mod = self.service.release.refresh(self.game, source.mod_id)
            except (OSError, ValueError):
                continue  # Offline is fine; d reports the error when asked.
            self._announce_update(mod)
        self.app.call_from_thread(self.reload)

    def _announce_update(self, mod: StagedMod) -> None:
        newer = pending_update(mod)
        if newer is None or mod.site != RELEASE_SITE:
            return
        self.notify(
            f"{mod.title} {newer.version} is out: uninstall (u), then d and i "
            "to update.",
            timeout=UPDATE_SECONDS,
        )
