"""Compose a mod workspace with independent files and artwork panes."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Static

from omamods.tui.preview import PicturePreview
from omamods.tui.file_table import ModFilesTable
from omamods.staging import StagedMod
from omamods.tui.mod_inspector import mod_overview, selected_file_summary


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


class ModDetail(Horizontal):
    """Own the two detail splits; e.g. ``yield ModDetail()``."""

    current_mod: StagedMod | None = None

    def compose(self) -> ComposeResult:
        yield from mod_detail_panes()

    def show_mod(self, mod: StagedMod) -> None:
        """Refresh facts with the file table; e.g. ``detail.show_mod(staged)``."""
        self.current_mod = mod
        table = self.query_one(ModFilesTable)
        table.show_mod(mod)
        self.query_one("#mod-overview", Static).update(mod_overview(mod))
        self._inspect_file(table.cursor_row)

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
