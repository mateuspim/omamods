"""Retry, remove, and clear actions shared by the queue screen and panel."""

import time

from textual import work
from textual.dom import DOMNode

from omamods.download_queue import DownloadStatus, shown_state
from omamods.tui.download_rows import RETRYABLE_STATES, retry_outcome
from omamods.tui.service import ModsService


class QueueActions(DOMNode):
    """Mix into a queue view that has ``service``, ``selected_status``, and
    ``refresh_queue``; e.g. ``class DownloadsPanel(QueueActions, Vertical)``.
    """

    service: ModsService

    def selected_status(self) -> DownloadStatus | None:
        """The highlighted entry; e.g. ``view.selected_status()``."""
        raise NotImplementedError

    def refresh_queue(self) -> None:
        """Re-read the queue; e.g. ``view.refresh_queue()``."""
        raise NotImplementedError

    def action_retry(self) -> None:
        status = self.selected_status()
        if status is None:
            return
        if shown_state(status, time.time()) not in RETRYABLE_STATES:
            self.notify(f"{status.file_name} is {status.state}; nothing to retry.")
            return
        self._retry_worker(status)

    @work(thread=True)
    def _retry_worker(self, status: DownloadStatus) -> None:
        try:
            message = retry_outcome(self.service, status)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)
            return
        if message is not None:
            self.notify(message)

    def action_clear(self) -> None:
        count = self.service.clear_finished_downloads()
        self.notify(f"Cleared {count} finished download(s).")
        self.refresh_queue()

    def action_remove(self) -> None:
        status = self.selected_status()
        if status is None:
            return
        try:
            self.service.remove_download(status)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="warning")
            return
        self.notify(f"Removed {status.file_name} from the queue.")
        self.refresh_queue()

    def action_clear_all(self) -> None:
        count = self.service.clear_download_queue()
        self.notify(f"Cleared {count} download(s); active transfers keep going.")
        self.refresh_queue()
