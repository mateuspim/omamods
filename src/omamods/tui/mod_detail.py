"""Compose a mod workspace with independent files and artwork panes."""

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from rich.text import Text
from textual.widgets import DataTable, Static

from omamods.tui.preview import PicturePreview
from omamods.tui.file_table import ModFilesTable
from omamods.staging import StagedMod
from omamods.pak_games import PakOverlayGame
from omamods.tui.mod_inspector import (
    collision_summary,
    mod_overview,
    selected_file_summary,
)
from omamods.tui.service import ModsService


def mod_detail_panes() -> ComposeResult:
    """Keep file actions above the fold; e.g. ``yield from mod_detail_panes()``."""
    with Vertical(id="detail"):
        yield Static(
            "Your next great playthrough starts here.\nAdd a mod with a or :add <url>.",
            id="details",
            markup=False,
        )
        yield ModFilesTable()
    with Vertical(id="preview-pane"):
        yield PicturePreview(id="picture")
        yield Static("o full picture   ·   w mod page", classes="preview-caption")
        yield Static("OVERVIEW", classes="inspector-label")
        yield Static("Your mod collection, at a glance.", id="mod-overview")
        yield Static("SELECTED FILE", classes="inspector-label")
        yield Static("Choose a file to inspect its details.", id="file-inspector")
        yield Static("COLLISIONS", classes="inspector-label")
        yield Static("Install a mod to check its assets.", id="mod-collisions")


class ModDetail(Horizontal):
    """Own the two detail splits; e.g. ``yield ModDetail(service, game)``."""

    current_mod: StagedMod | None = None

    def __init__(self, service: ModsService, game: PakOverlayGame) -> None:
        super().__init__()
        self.service = service
        self.game = game

    def compose(self) -> ComposeResult:
        yield from mod_detail_panes()

    def show_mod(self, mod: StagedMod) -> None:
        """Refresh facts with the file table; e.g. ``detail.show_mod(staged)``."""
        self.current_mod = mod
        table = self.query_one(ModFilesTable)
        table.show_mod(mod)
        self.query_one("#mod-overview", Static).update(mod_overview(mod))
        self._inspect_file(table.cursor_row)
        self._check_collisions(mod)

    @work(thread=True, group="collisions")
    def _check_collisions(self, mod: StagedMod) -> None:
        # Reads pak indexes from the game folder, so keep it off the UI thread.
        try:
            report = self.service.conflicts.for_mod(self.game, mod)
        except (OSError, ValueError) as error:
            summary = Text(f"Could not check collisions: {error}", style="red")
        else:
            summary = collision_summary(report, mod.title)
        self.app.call_from_thread(self._show_collisions, mod, summary)

    def _show_collisions(self, mod: StagedMod, summary: Text) -> None:
        if mod is self.current_mod:  # A newer selection has its own check.
            self.query_one("#mod-collisions", Static).update(summary)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._inspect_file(event.cursor_row)

    def _inspect_file(self, row: int) -> None:
        mod = self.current_mod
        if mod is None or not mod.files:
            self.query_one("#file-inspector", Static).update(
                "No files listed for this mod."
            )
            return
        file = mod.files[min(row, len(mod.files) - 1)]
        self.query_one("#file-inspector", Static).update(
            selected_file_summary(mod, file)
        )
