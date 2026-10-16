"""The mods screen's downloads panel: a summary bar that grows in two steps.

``D`` cycles minimized (one summary line for every game) → this game's queue
(a short table under the mods) → the whole queue filling the screen.
"""

import time

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from omamods.download_queue import DownloadStatus
from omamods.pak_games import PakOverlayGame
from omamods.tui.download_rows import (
    QUEUE_COLUMNS,
    DownloadTitles,
    queue_cells,
    queue_summary,
)
from omamods.tui.queue_actions import QueueActions
from omamods.tui.service import ModsService

MINIMIZED = "minimized"
GAME_QUEUE = "game"
FULL_QUEUE = "full"
PANEL_MODES = (MINIMIZED, GAME_QUEUE, FULL_QUEUE)


def next_panel_mode(mode: str) -> str:
    """Step to the next size; e.g. ``next_panel_mode('minimized') == 'game'``."""
    if mode not in PANEL_MODES:
        raise ValueError(f"panel mode={mode!r}: expected one of {PANEL_MODES!r}")
    return PANEL_MODES[(PANEL_MODES.index(mode) + 1) % len(PANEL_MODES)]


def panel_statuses(
    statuses: tuple[DownloadStatus, ...], mode: str, game_id: str
) -> tuple[DownloadStatus, ...]:
    """Rows the table shows; e.g. ``panel_statuses(s, 'game', 'cyberpunk-2077')``."""
    if mode == FULL_QUEUE:
        return statuses
    if mode == GAME_QUEUE:
        return tuple(status for status in statuses if status.game_id == game_id)
    return ()


def panel_title(mode: str, game_name: str) -> str:
    """Name the panel and its next step; e.g. ``panel_title('game', 'Cronos')``."""
    titles = {
        MINIMIZED: "Downloads · D: this game's queue",
        GAME_QUEUE: f"Downloads · {game_name} · D: all games",
        FULL_QUEUE: "Downloads · all games · r retry, c clear · D: minimize",
    }
    return titles[mode]


class DownloadsPanel(QueueActions, Vertical):
    """Show the queue under the mods; e.g. ``DownloadsPanel(service, cyberpunk)``."""

    BINDINGS = [
        Binding("r", "retry", "Retry download"),
        Binding("c", "clear", "Clear finished"),
    ]

    def __init__(self, service: ModsService, game: PakOverlayGame) -> None:
        super().__init__(id="downloads-panel", classes=MINIMIZED)
        self.service = service
        self.game = game
        self.mode = MINIMIZED
        self.statuses: tuple[DownloadStatus, ...] = ()
        self.shown: tuple[DownloadStatus, ...] = ()
        self.titles = DownloadTitles(service)

    def compose(self) -> ComposeResult:
        yield Static(id="downloads-bar", markup=False)
        yield DataTable(id="downloads-table", cursor_type="row")

    def on_mount(self) -> None:
        self.query_one("#downloads-table", DataTable).add_columns(*QUEUE_COLUMNS)
        self.set_mode(MINIMIZED)

    def set_mode(self, mode: str) -> None:
        """Resize the panel; for example, ``panel.set_mode('full')``."""
        if mode not in PANEL_MODES:
            raise ValueError(f"panel mode={mode!r}: expected one of {PANEL_MODES!r}")
        self.remove_class(self.mode).add_class(mode)
        self.mode = mode
        self.border_title = (
            "" if mode == MINIMIZED else panel_title(mode, self.game.name)
        )
        self.tooltip = panel_title(mode, self.game.name)
        self.refresh_queue()

    def cycle(self) -> str:
        """Grow, or shrink back after full; e.g. ``panel.cycle() == 'game'``."""
        self.set_mode(next_panel_mode(self.mode))
        return self.mode

    def refresh_queue(self) -> None:
        """Re-read the shared queue; for example, ``panel.refresh_queue()``."""
        try:
            self.statuses = self.service.downloads()
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error")
            return
        now = time.time()
        summary = queue_summary(self.statuses, self.game.game_id, self.titles, now)
        self.query_one("#downloads-bar", Static).update(summary)
        self._fill_table(panel_statuses(self.statuses, self.mode, self.game.game_id))

    def _fill_table(self, shown: tuple[DownloadStatus, ...]) -> None:
        self.shown = shown
        table = self.query_one("#downloads-table", DataTable)
        row, now = table.cursor_row, time.time()
        table.clear()
        for status in shown:
            table.add_row(
                *queue_cells(status, self.titles(status), now), key=status.key
            )
        if shown:
            table.move_cursor(row=min(row, len(shown) - 1))

    def selected_status(self) -> DownloadStatus | None:
        """The highlighted row; e.g. ``panel.selected_status()``."""
        if not self.shown:
            self.notify("No downloads shown here.")
            return None
        return self.shown[self.query_one("#downloads-table", DataTable).cursor_row]
