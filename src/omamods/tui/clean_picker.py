"""Pick which games "clean everything" (C) resets, and see each one's mods.

Every game starts ticked; the panel beside the list shows the highlighted
game's mods and files, so a game can be checked before it is left in or out.
"""

from collections.abc import Iterable, Mapping
from itertools import groupby
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, SelectionList, Static

from omamods.clean_all import CLEAN_NOTE, GameClean
from omamods.untracked_mods import record_files

ModTitles = Mapping[tuple[str, int], str]
INDENT = "  "


def mod_count(game: GameClean) -> int:
    """Count distinct recorded mods; e.g. ``mod_count(game)``."""
    return len({(owned.site, owned.mod_id) for owned in game.records})


def game_label(game: GameClean) -> str:
    """Count first, so a long title never hides it; e.g. ``game_label(game)``."""
    files = len(game.tracked) + len(game.untracked)
    return f"{files:>4} files  {game.name}"


def _shown(path: Path, root: Path | None) -> str:
    if root is not None and path.is_relative_to(root):
        return str(path.relative_to(root))
    return str(path)


def folder_lines(paths: Iterable[Path], root: Path | None) -> list[str]:
    """List files under their folder; e.g. ``folder_lines(files, game_root)``.

    Mod paths are long and unbroken, so a full path per line wrapped badly in
    narrow terminals; one folder line then bare names stays readable.
    """
    lines: list[str] = []
    ordered = sorted(paths, key=lambda path: (path.parent, path.name))
    for folder, files in groupby(ordered, key=lambda path: path.parent):
        lines.append(f"{INDENT}{_shown(folder, root)}/")
        lines.extend(f"{INDENT * 2}{file.name}" for file in files)
    return lines


def _mod_lines(game: GameClean, titles: ModTitles) -> list[str]:
    lines: list[str] = []
    for site, mod_id in sorted({(o.site, o.mod_id) for o in game.records}):
        title = titles.get((site, mod_id), f"mod {mod_id}")
        lines.append(f"▸ {title}  [{site} {mod_id}]")
        records = (
            o.record for o in game.records if (o.site, o.mod_id) == (site, mod_id)
        )
        files = {path for record in records for path in record_files(record)}
        lines.extend(folder_lines(files, game.game.install_root))
    return lines


def _summary(game: GameClean) -> str:
    mods, stray = mod_count(game), len(game.untracked)
    return f"{mods} mod(s) from OmaMods · {stray} file(s) with no install record"


def game_detail(game: GameClean, titles: ModTitles) -> str:
    """List a game's mods and files; e.g. ``game_detail(game, {('nexus', 1): 'A'})``."""
    root = game.game.install_root
    lines = [game.name, _summary(game), f"Folder: {root or 'unknown'}", ""]
    if game.records:
        lines.append("Installed by OmaMods (uninstalled; a copy is kept):")
        lines.extend(_mod_lines(game, titles))
    if game.untracked:
        if game.records:
            lines.append("")
        lines.append("No install record (moved aside):")
        lines.extend(folder_lines(game.untracked, root))
    return "\n".join(lines)


class CleanPicker(ModalScreen[tuple[GameClean, ...] | None]):
    """Tick games to reset; e.g. ``push_screen(CleanPicker(plan, titles), done)``."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Clean ticked games", priority=True),
        Binding("a", "toggle_all", "Tick all or none"),
        Binding("j", "move(1)", "Down", show=False),
        Binding("k", "move(-1)", "Up", show=False),
    ]

    def __init__(self, plan: tuple[GameClean, ...], titles: ModTitles) -> None:
        super().__init__()
        self.plan = plan
        self.titles = titles

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog large"):
            yield Label(
                "Clean everything: tick the games to reset", classes="dialog-title"
            )
            with Horizontal(id="clean-picker"):
                yield SelectionList[str](
                    *((game_label(g), g.key, True) for g in self.plan), id="clean-games"
                )
                with VerticalScroll(id="clean-detail"):
                    yield Static(id="clean-files", markup=False)
            yield Static(CLEAN_NOTE, classes="hint")
            yield Static(
                "j/k move, Space ticks, a ticks all or none, "
                "Enter cleans the ticked games, Esc cancels",
                classes="hint",
            )

    def on_mount(self) -> None:
        if self.plan:
            self.show_game(self.plan[0].key)

    def show_game(self, key: str) -> None:
        """Show one game's mods beside the list; e.g. ``picker.show_game('sb')``."""
        game = next((g for g in self.plan if g.key == key), None)
        if game is not None:
            self.query_one("#clean-files", Static).update(
                game_detail(game, self.titles)
            )

    def on_selection_list_selection_highlighted(
        self, event: SelectionList.SelectionHighlighted[str]
    ) -> None:
        self.show_game(event.selection.value)

    def ticked(self) -> tuple[GameClean, ...]:
        """List the ticked games in plan order; e.g. ``picker.ticked()``."""
        chosen = set(self.query_one(SelectionList).selected)
        return tuple(game for game in self.plan if game.key in chosen)

    def action_move(self, step: int) -> None:
        games = self.query_one(SelectionList)
        if step > 0:
            games.action_cursor_down()
        else:
            games.action_cursor_up()

    def action_toggle_all(self) -> None:
        games = self.query_one(SelectionList)
        if len(games.selected) == len(self.plan):
            games.deselect_all()
        else:
            games.select_all()

    def action_confirm(self) -> None:
        chosen = self.ticked()
        if not chosen:
            self.notify("Tick at least one game, or press Esc to cancel.")
            return
        self.dismiss(chosen)

    def action_cancel(self) -> None:
        self.dismiss(None)
