"""The download queue: progress, speed, and stalls for every staged download."""

import time

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Static

from omamods.download_queue import STALL_SECONDS, DownloadStatus
from omamods.tui.commands import CommandSpec
from omamods.tui.download_rows import QUEUE_COLUMNS, DownloadTitles, queue_cells
from omamods.tui.queue_actions import QueueActions
from omamods.tui.service import ModsService
from omamods.tui.workspace import (
    WorkspaceHeader,
    WorkspaceHints,
    WorkspaceScreen,
    WorkspaceStatus,
)

REFRESH_SECONDS = 1.0


class DownloadsScreen(QueueActions, WorkspaceScreen):
    """Watch every download; e.g. ``app.push_screen(DownloadsScreen(service))``."""

    BINDINGS = [
        Binding("r", "retry", "Retry"),
        Binding("c", "clear", "Clear finished"),
        Binding("escape", "app.pop_screen", "Back"),
    ]
    SCREEN_COMMANDS = (
        CommandSpec("retry", ("r",), ":retry", "retry the selected download"),
        CommandSpec("clear", ("c",), ":clear", "clear done and failed downloads"),
    )

    def __init__(self, service: ModsService) -> None:
        super().__init__()
        self.service = service
        self.statuses: tuple[DownloadStatus, ...] = ()
        self.titles = DownloadTitles(service)

    def compose(self) -> ComposeResult:
        yield WorkspaceHeader("Downloads", "TRANSFER QUEUE")
        yield DataTable(id="queue", cursor_type="row", zebra_stripes=True)
        yield Static(
            f"Stalled = no data for {STALL_SECONDS:.0f}s. "
            "r retries the selected download, c clears done and failed ones.",
            id="queue-help",
            markup=False,
        )
        yield WorkspaceStatus("Downloads")
        yield WorkspaceHints(
            "[b]r[/] retry   [b]c[/] clear finished   [b]j/k[/] navigate   "
            "[b]esc[/] back"
        )

    def on_mount(self) -> None:
        self.sub_title = "Downloads"
        table = self.query_one("#queue", DataTable)
        table.border_title = "Download queue"
        table.add_columns(*QUEUE_COLUMNS)
        self.refresh_queue()
        self.set_interval(REFRESH_SECONDS, self.refresh_queue)

    def refresh_queue(self) -> None:
        """Re-read the queue folder; for example, ``screen.refresh_queue()``."""
        try:
            self.statuses = self.service.downloads()
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error")
            return
        table = self.query_one("#queue", DataTable)
        row, now = table.cursor_row, time.time()
        table.clear()
        for status in self.statuses:
            table.add_row(
                *queue_cells(status, self.titles(status), now), key=status.key
            )
        if self.statuses:
            table.move_cursor(row=min(row, len(self.statuses) - 1))

    def selected_status(self) -> DownloadStatus | None:
        """The highlighted entry; e.g. ``screen.selected_status()``."""
        if not self.statuses:
            self.notify("The queue is empty.")
            return None
        return self.statuses[self.query_one("#queue", DataTable).cursor_row]

    def run_command(self, name: str, args: tuple[str, ...]) -> None:
        """Run a ':' command; for example, ``screen.run_command('retry', ())``."""
        if name == "retry":
            self.action_retry()
        else:
            self.action_clear()
