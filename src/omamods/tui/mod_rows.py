"""Render the mods list's rows: an install mark and the mod's name."""

from rich.table import Table

from omamods.staging import StagedMod
from omamods.tui.list_filter import mark_matches

INSTALLED_MARK = ("●", "green")
STAGED_MARK = ("○", "bright_black")


def mod_mark(mod: StagedMod) -> tuple[str, str]:
    """Mark mods with any installed file; e.g. ``mod_mark(mod) == ('●', 'green')``."""
    return INSTALLED_MARK if mod.installed else STAGED_MARK


def mod_prompt(mod: StagedMod, query: str = "") -> Table:
    """Render one mods-list row; e.g. ``Option(mod_prompt(mod, 'hair'), id=key)``."""
    mark, colour = mod_mark(mod)
    row = Table.grid(expand=True, padding=(0, 1))
    row.add_column(width=1, style=colour)
    row.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    row.add_row(mark, mark_matches(mod.title, query))
    return row
