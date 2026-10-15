"""Render the mods screen's rows: the mods list, details, and file table."""

from rich.table import Table

from omamods.mod_sites import AYAKA_SITE
from omamods.nexus_api import NexusFile
from omamods.staging import StagedMod
from omamods.tui.list_filter import mark_matches, matches_query

INSTALLED_MARK = ("●", "green")
STAGED_MARK = ("○", "bright_black")
ADULT_BADGE = ("18+", "bold red")


def mod_mark(mod: StagedMod) -> tuple[str, str]:
    """Mark mods with any installed file; e.g. ``mod_mark(mod) == ('●', 'green')``."""
    return INSTALLED_MARK if mod.installed else STAGED_MARK


def mod_prompt(mod: StagedMod, query: str = "", adult: bool = False) -> Table:
    """Render one mods-list row; e.g. ``Option(mod_prompt(mod, 'hair'), id=key)``."""
    mark, colour = mod_mark(mod)
    row = Table.grid(expand=True, padding=(0, 1))
    row.add_column(width=1, style=colour)
    row.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    row.add_column(no_wrap=True, style=ADULT_BADGE[1])
    row.add_row(mark, mark_matches(mod.title, query), ADULT_BADGE[0] if adult else "")
    return row


def visible_mods(
    mods: tuple[StagedMod, ...], query: str, hidden: frozenset[str]
) -> tuple[StagedMod, ...]:
    """Keep mods matching query and not hidden; e.g. ``visible_mods(ms, 'hair', set())``."""
    return tuple(
        m for m in mods if matches_query(m.title, query) and mod_key(m) not in hidden
    )


def describe_mod(mod: StagedMod, adult: bool = False) -> str:
    """Render the details panel; for example, ``describe_mod(staged, adult=True)``."""
    note = "\n\n18+ NSFW · m unmarks · H cycles blur, hide, show" if adult else ""
    if mod.info is None:
        return f"{mod.title}\nNo page details yet; press a and paste its URL.{note}"
    info = mod.info
    # AyakaMods asks integrations to credit it as the source.
    site = "from AyakaMods" if mod.site == AYAKA_SITE else ""
    byline = " · ".join(part for part in (info.author, info.version, site) if part)
    return f"{info.name}\n{byline}\n\n{info.summary}".strip() + note


def file_cells(mod: StagedMod, file: NexusFile) -> tuple[str, ...]:
    """Render one file row; for example, ``file_cells(staged, file)``."""
    size = f"{file.size_kb / 1024:.1f} MB" if file.size_kb else ""
    # Status first: long Nexus file names used to push it off-screen.
    return (
        "yes" if file.file_id in mod.installed else "",
        "yes" if file.file_id in mod.archives else "",
        file.category,
        file.version,
        size,
        file.display_name or file.file_name,
        str(file.file_id),
    )


def mod_key(mod: StagedMod) -> str:
    """Name a mod uniquely across sites; e.g. ``mod_key(staged) == 'ayaka:7311'``."""
    return f"{mod.site}:{mod.mod_id}"
