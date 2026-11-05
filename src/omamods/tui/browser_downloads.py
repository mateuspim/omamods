"""Track downloads Nexus sends through the browser, and the queue shown for them.

Nexus without Premium only serves files through its web page, so OmaMods opens
one page at a time, hides it while the file arrives, and moves on. Split from
service.py, which passed the 500-line limit.
"""

from typing import TYPE_CHECKING

from omamods.browser_hiding import HiddenWindows
from omamods.browser_queue import STAY, BrowserQueue
from omamods.download_queue import DOWNLOADING, QUEUED, DownloadStatus, shown_state
from omamods.mod_fetch import download_log
from omamods.mod_sites import NEXUS_SITE
from omamods.nexus_api import NexusFile, describe_nexus_file
from omamods.pak_games import PakOverlayGame
from omamods.staging import StagedMod

if TYPE_CHECKING:
    from omamods.tui.service import ModsService


class BrowserDownloads:
    """Queue and browser windows; e.g. service.browser_downloads.downloads()."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service
        self.browser_queue = BrowserQueue()
        self.hidden_windows = HiddenWindows()

    def await_file(
        self, game: PakOverlayGame, mod_id: int, file_id: int, url: str
    ) -> None:
        """Open a file's Nexus page once; e.g. browser_downloads.await_file(sb, 1, 7, url)."""
        staged = self.service.staged_mod(game, mod_id).archives.keys()
        if self.browser_queue.add(game.game_id, mod_id, file_id, url, staged):
            self.service.open_nexus(url)

    def advance_browser_downloads(self) -> tuple[str, ...]:
        """Move Nexus windows on as files arrive; e.g. ``service.advance_browser_downloads()``."""
        messages: list[str] = []
        for game_id, mod_id in list(self.browser_queue.pending):
            game = self.service.catalog.get(game_id)
            mod = self.service.staged_mod(game, mod_id)
            step = self.browser_queue.advance(game_id, mod_id, mod.archives.keys())
            messages.extend(self._surprise_messages(game_id, mod, step.unexpected))
            if step.action == STAY:
                continue
            self.service.close_nexus_window(game, mod_id)
            self.hidden_windows.forget((game_id, mod_id))
            if step.url is None:
                messages.append(f"{mod.title}: all files downloaded; closed Nexus")
                continue
            self.service.open_nexus(step.url)
            messages.append(f"{mod.title}: file arrived; opening the next one")
        return tuple(messages) + self._move_browser_windows()

    def _move_browser_windows(self) -> tuple[str, ...]:
        waiting = self.browser_queue.waiting_files()
        if not waiting:
            return ()
        statuses = self.downloads()
        for game_id, mod_id in self.hidden_windows.to_hide(waiting, statuses):
            self.service.windows.hide_mod(
                self.service.catalog.get(game_id).nexus_domain, mod_id
            )
        restored = self.hidden_windows.to_restore(waiting, statuses)
        return tuple(
            self._reopen_popup(game_id, mod_id) for game_id, mod_id in restored
        )

    def _reopen_popup(self, game_id: str, mod_id: int) -> str:
        game = self.service.catalog.get(game_id)
        self.service.close_nexus_window(game, mod_id)
        url = self.browser_queue.waiting_url(game_id, mod_id)
        if url is not None:
            self.service.open_nexus(url)
        title = self.service.staged_mod(game, mod_id).title
        return f"{title}: download failed; reopened Nexus so you can click again"

    def _surprise_messages(
        self, game_id: str, mod: StagedMod, unexpected: tuple[int, ...]
    ) -> list[str]:
        names = {f.file_id: describe_nexus_file(f) for f in mod.files}
        waiting = self.browser_queue.waiting_for(game_id, mod.mod_id)
        still = f"; still waiting for {names.get(waiting, waiting)}" if waiting else ""
        return [
            f"{mod.title}: Nexus sent {names.get(file_id, file_id)}, which you did not "
            f"ask for{still}. Select it and press x to remove it."
            for file_id in unexpected
        ]

    def mark_queued(
        self, game: PakOverlayGame, mod_id: int, files: tuple[NexusFile, ...]
    ) -> None:
        """Show files as queued before they start; e.g. ``mark_queued(sb, 1, files)``."""
        log = download_log(self.service.settings.storage_root)
        staged = self.service.staged_mod(game, mod_id).archives
        for file in files:
            if file.file_id not in staged:
                log.begin(game.game_id, mod_id, file, QUEUED)

    def downloads(self) -> tuple[DownloadStatus, ...]:
        """Read the shared queue, newest first; e.g. ``service.downloads()``."""
        return download_log(self.service.settings.storage_root).statuses()

    def clear_finished_downloads(self) -> int:
        """Drop done and failed entries; e.g. ``service.clear_finished_downloads()``."""
        return download_log(self.service.settings.storage_root).clear_finished()

    def remove_download(self, status: DownloadStatus) -> None:
        """Drop one entry and its Nexus popup; e.g. ``service.remove_download(s)``."""
        log = download_log(self.service.settings.storage_root)
        if shown_state(status, log.clock()) == DOWNLOADING:
            raise ValueError(
                f"download={status.file_name!r} is still receiving data; "
                "expected a queued, waiting, stalled, done, or failed entry"
            )
        log.remove(status)
        # Ayaka numbers mods on its own, so its IDs could match a Nexus popup's.
        if status.site == NEXUS_SITE:
            self._forget_browser_file(status.game_id, status.mod_id, status.file_id)

    def clear_download_queue(self) -> int:
        """Drop all but moving downloads; e.g. ``service.clear_download_queue()``."""
        count = download_log(self.service.settings.storage_root).clear_idle()
        live = {
            (s.game_id, s.mod_id, s.file_id)
            for s in self.downloads()
            if s.site == NEXUS_SITE
        }
        for (game_id, mod_id), queue in list(self.browser_queue.pending.items()):
            for file_id, _ in list(queue):
                if (game_id, mod_id, file_id) not in live:
                    self._forget_browser_file(game_id, mod_id, file_id)
        return count

    def _forget_browser_file(self, game_id: str, mod_id: int, file_id: int) -> None:
        step = self.browser_queue.drop(game_id, mod_id, file_id)
        if step.action == STAY:
            return
        self.service.close_nexus_window(self.service.catalog.get(game_id), mod_id)
        self.hidden_windows.forget((game_id, mod_id))
        if step.url is not None:
            self.service.open_nexus(step.url)
