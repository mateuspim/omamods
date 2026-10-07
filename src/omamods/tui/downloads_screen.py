"""The download queue: progress, speed, and stalls for every staged download."""

import time

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from omamods.download_queue import (
    DONE,
    DOWNLOADING,
    STALL_SECONDS,
    DownloadStatus,
    shown_state,
)
from omamods.pak_games import pak_overlay_game
from omamods.tui.commands import CommandSpec
from omamods.tui.service import ModsService

REFRESH_SECONDS = 1.0
RETRYABLE_STATES = frozenset({"failed", "stalled", "waiting for browser", "queued"})


def human_bytes(count: float) -> str:
    """Format sizes; for example, ``human_bytes(1536) == '1.5 KB'``."""
    for unit in ("B", "KB", "MB", "GB"):
        if count < 1024 or unit == "GB":
            return f"{count:.0f} {unit}" if unit == "B" else f"{count:.1f} {unit}"
        count /= 1024
    return f"{count:.1f} GB"


def progress_text(status: DownloadStatus) -> str:
    """Show bytes and percent; e.g. ``progress_text(status)``."""
    if status.state == DONE:
        return human_bytes(status.received or status.total or 0)
    if not status.total:
        return human_bytes(status.received)
    percent = 100 * status.received / status.total
    return (
        f"{percent:.0f}%  {human_bytes(status.received)} / {human_bytes(status.total)}"
    )


def eta_text(status: DownloadStatus) -> str:
    """Estimate time left; for example, ``eta_text(status)``."""
    if status.state != DOWNLOADING or not status.total or status.bytes_per_second <= 0:
        return ""
    seconds = int((status.total - status.received) / status.bytes_per_second)
    return f"{seconds // 60}m {seconds % 60:02d}s"


def queue_cells(status: DownloadStatus, title: str, now: float) -> tuple[str, ...]:
    """Render one queue row; for example, ``queue_cells(status, 'Suit', now)``."""
    state = shown_state(status, now)
    active = status.state == DOWNLOADING
    return (
        state,
        title,
        status.file_name,
        progress_text(status),
        f"{human_bytes(status.bytes_per_second)}/s" if active else "",
        eta_text(status),
        f"{now - status.progressed:.0f}s ago" if active else "",
        status.error,
    )


class DownloadsScreen(Screen[None]):
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
        self.titles: dict[tuple[str, int], str] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="queue", cursor_type="row")
        yield Static(
            f"Stalled = no data for {STALL_SECONDS:.0f}s. "
            "r retries the selected download, c clears done and failed ones.",
            id="queue-help",
            markup=False,
        )
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "Downloads"
        table = self.query_one("#queue", DataTable)
        table.add_columns(
            "State", "Mod", "File", "Progress", "Speed", "ETA", "Last data", "Error"
        )
        self.refresh_queue()
        self.set_interval(REFRESH_SECONDS, self.refresh_queue)

    def _title(self, status: DownloadStatus) -> str:
        key = (status.game_id, status.mod_id)
        if key not in self.titles:
            try:
                game = pak_overlay_game(status.game_id)
                title = self.service.staged_mod(game, status.mod_id).title
            except ValueError:
                title = f"{status.game_id} mod {status.mod_id}"
            self.titles[key] = title
        return self.titles[key]

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
                *queue_cells(status, self._title(status), now), key=status.key
            )
        if self.statuses:
            table.move_cursor(row=min(row, len(self.statuses) - 1))

    def _selected(self) -> DownloadStatus | None:
        if not self.statuses:
            self.notify("The queue is empty.")
            return None
        return self.statuses[self.query_one("#queue", DataTable).cursor_row]

    def action_retry(self) -> None:
        status = self._selected()
        if status is None:
            return
        if shown_state(status, time.time()) not in RETRYABLE_STATES:
            self.notify(f"{status.file_name} is {status.state}; nothing to retry.")
            return
        self._retry_worker(status)

    @work(thread=True)
    def _retry_worker(self, status: DownloadStatus) -> None:
        try:
            staged = self.service.retry(status)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)
            return
        if not staged:
            self.notify(f"{status.file_name}: click 'Mod Manager Download' on Nexus.")

    def run_command(self, name: str, args: tuple[str, ...]) -> None:
        """Run a ':' command; for example, ``screen.run_command('retry', ())``."""
        if name == "retry":
            self.action_retry()
        else:
            self.action_clear()

    def action_clear(self) -> None:
        count = self.service.clear_finished_downloads()
        self.notify(f"Cleared {count} finished download(s).")
        self.refresh_queue()
