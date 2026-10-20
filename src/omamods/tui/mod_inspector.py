"""Readable mod and file facts for the artwork-side inspector."""

from rich.text import Text

from omamods.asset_collisions import describe_collision
from omamods.mod_sites import AYAKA_SITE
from omamods.nexus_api import NexusFile
from omamods.staging import StagedMod
from omamods.tui.asset_conflicts import CollisionReport
from omamods.tui.mod_rows import file_cells, file_next_action

LOAD_ORDER_NOTE = "Later wins: _<n>_P number, then name order (z_ loads last)."


def mod_overview(mod: StagedMod) -> Text:
    """Summarise a mod's local state; e.g. ``mod_overview(staged)``."""
    text = Text()
    text.append(
        f"{len(mod.installed):02} installed  /  {len(mod.files):02} files",
        style="bold cyan",
    )
    source = "AyakaMods" if mod.site == AYAKA_SITE else "Nexus Mods"
    text.append(f"\n{source}  ·  #{mod.mod_id}", style="dim")
    if mod.info is not None and mod.info.author:
        text.append(f"\nby {mod.info.author}")
    return text


def selected_file_summary(mod: StagedMod, file: NexusFile) -> Text:
    """Explain the highlighted file and next action; e.g. ``selected_file_summary(mod, f)``."""
    cells = file_cells(mod, file)
    text = Text()
    text.append(file.display_name or file.file_name, style="bold")
    text.append(f"\n{file.category}  ·  {file.version or 'unversioned'}", style="dim")
    text.append("\n\n")
    text.append_text(Text.assemble(cells[0]))
    if cells[4]:
        text.append(f"  ·  {cells[4]}", style="dim")
    action = f"enter  {file_next_action(mod, file)} this file"
    return text.append(f"\n\n{action}", style="cyan")


def collision_lines(report: CollisionReport, owner: str) -> tuple[str, ...]:
    """One line per clash or unread index; e.g. ``collision_lines(r, 'Hero')``."""
    lines = tuple(describe_collision(c, owner) for c in report.collisions)
    return lines + tuple(f"not checked: {entry}" for entry in report.unreadable)


def collision_summary(report: CollisionReport, owner: str) -> Text:
    """Show clashes in the inspector; e.g. ``collision_summary(report, 'Hero')``."""
    lines = collision_lines(report, owner)
    if not lines:
        return Text("No asset collisions with installed mods.", style="dim")
    text = Text()
    for line in lines:
        text.append(f"! {line}\n", style="yellow")
    return text.append(LOAD_ORDER_NOTE, style="dim")


def collision_warning(report: CollisionReport, owner: str) -> str:
    """Warn before an install; e.g. ``collision_warning(report, 'Hero')``."""
    lines = collision_lines(report, owner)
    if not lines:
        return ""
    listed = "\n".join(f"  {line}" for line in lines)
    return f"\n\nAsset collisions (likely load order):\n{listed}\n{LOAD_ORDER_NOTE}"
