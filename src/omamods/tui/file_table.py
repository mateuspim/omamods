"""Keep filenames and install state readable as the workspace splits resize."""

from textual import events
from textual.widgets import DataTable

from omamods.staging import StagedMod
from omamods.tui.mod_rows import file_cells


def file_column_widths(width: int) -> tuple[tuple[str, int], ...]:
    """Fit essential columns first; e.g. ``file_column_widths(45)``."""
    if width < 68:
        return (("State", 9), ("File", max(4, width - 25)), ("Kind", 8))
    return (
        ("State", 9),
        ("File", width - 50),
        ("Category", 8),
        ("Version", 7),
        ("Size", 8),
        ("ID", 4),
    )


class ModFilesTable(DataTable):
    """Own file rendering and preserve its cursor; e.g. ``table.show_mod(mod)``."""

    def __init__(self) -> None:
        super().__init__(id="files", cursor_type="row", zebra_stripes=True)
        self.mod: StagedMod | None = None
        self.column_layout: tuple[tuple[str, int], ...] = ()

    def on_resize(self, event: events.Resize) -> None:
        layout = file_column_widths(event.size.width)
        if layout != self.column_layout:
            self.column_layout = layout
            self._fill_files()

    def show_mod(self, mod: StagedMod) -> None:
        """Show a mod's file choices; e.g. ``table.show_mod(staged)``."""
        self.mod = mod
        self._fill_files()

    def _fill_files(self) -> None:
        row = self.cursor_row
        self.clear(columns=True)
        for label, width in self.column_layout:
            self.add_column(label, width=width)
        if self.mod is None or not self.column_layout:
            return
        for file in self.mod.files:
            cells = file_cells(self.mod, file)[: len(self.column_layout)]
            self.add_row(*cells, key=str(file.file_id))
        if self.mod.files:
            self.move_cursor(row=min(row, len(self.mod.files) - 1))
