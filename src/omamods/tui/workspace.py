"""Shared workspace chrome and terminal-size rules for every main screen."""

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import DataTable, Input, OptionList, Static
from omamods.tui.command_bar import SearchPrompt
from omamods.tui.file_table import ModFilesTable
from omamods.tui.mod_rows import file_next_action


def cursor_location(widget: Widget | None) -> str:
    """Describe the active pane's cursor; e.g. ``cursor_location(table)``."""
    if isinstance(widget, OptionList):
        rows = [i for i, option in enumerate(widget.options) if not option.disabled]
        position = (
            rows.index(widget.highlighted) + 1 if widget.highlighted in rows else 0
        )
        return f"{position:02} / {len(rows):02}"
    if isinstance(widget, DataTable):
        position = widget.cursor_row + 1 if widget.row_count else 0
        return f"{position:02} / {widget.row_count:02}"
    return ""


def interaction_mode(screen: Screen[object], focused: Widget | None) -> str:
    """Name the current interaction; e.g. ``interaction_mode(screen, input)``."""
    if isinstance(focused, Input):
        if isinstance(screen, SearchPrompt):
            return "SEARCH"
        return "COMMAND" if focused.id == "command-line" else "INSERT"
    return "NORMAL"


class WorkspaceScreen(Screen[None]):
    """Adapt splits to the terminal; e.g. ``class Library(WorkspaceScreen)``."""

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 110, "compact-width")
        self.set_class(event.size.height < 32, "compact-height")


class WorkspaceHeader(Horizontal):
    """Brand and identify a workspace; e.g. ``WorkspaceHeader('Library', 'LOCAL')``."""

    def __init__(self, context: str, badge: str) -> None:
        super().__init__(classes="workspace-header")
        self.context = context
        self.badge = badge

    def compose(self) -> ComposeResult:
        yield Static("◈  OMAMODS", classes="workspace-brand")
        yield Static(self.context, classes="workspace-context", markup=False)
        yield Static(self.badge, classes="workspace-badge", markup=False)


class WorkspaceStatus(Horizontal):
    """Show mode, workspace, and cursor; e.g. ``WorkspaceStatus('Library')``."""

    def __init__(self, context: str) -> None:
        super().__init__(classes="workspace-status")
        self.context = context
        self.previous: tuple[str, str, str] | None = None

    def compose(self) -> ComposeResult:
        yield Static("NORMAL", classes="workspace-mode")
        yield Static(self.context, classes="workspace-path", markup=False)
        yield Static(classes="workspace-position", markup=False)

    def on_mount(self) -> None:
        self.refresh_state()
        self.set_interval(0.2, self.refresh_state)

    def refresh_state(self) -> None:
        """Reflect focus without host I/O; e.g. ``status.refresh_state()``."""
        focused = self.app.focused
        self._refresh_hints(focused)
        mode = interaction_mode(self.app.screen, focused)
        pane = (focused.id or "").replace("-", " ") if focused else ""
        position = f"{pane.upper()}  {cursor_location(focused)}".strip()
        state = (mode, self.screen.sub_title or self.context, position)
        if state == self.previous:
            return
        self.previous = state
        self.query_one(".workspace-mode", Static).update(mode)
        self.query_one(".workspace-mode").set_class(mode != "NORMAL", "editing")
        self.query_one(".workspace-path", Static).update(state[1])
        self.query_one(".workspace-position", Static).update(position)

    def _refresh_hints(self, focused: Widget | None) -> None:
        for hints in self.screen.query(WorkspaceHints):
            if hints.is_mounted:
                hints.refresh_context(focused)


class WorkspaceHints(Horizontal):
    """Keep only contextual keys visible; e.g. ``WorkspaceHints('enter open')``."""

    def __init__(self, hints: str) -> None:
        super().__init__(classes="workspace-hints")
        self.hints = hints
        self.current_hints = hints

    def compose(self) -> ComposeResult:
        yield Static(self.hints, classes="hints-context")
        yield Static("[b]space[/] actions   [b]:[/] command", classes="hints-global")

    def refresh_context(self, focused: Widget | None) -> None:
        """Show actions for the focused pane; e.g. ``hints.refresh_context(table)``."""
        hints = self.hints
        if isinstance(focused, ModFilesTable) and focused.mod and focused.mod.files:
            file = focused.mod.files[
                min(focused.cursor_row, len(focused.mod.files) - 1)
            ]
            action = file_next_action(focused.mod, file)
            hints = f"[b]enter[/] {action}   [b]d[/] download   [b]x[/] remove"
        elif focused is not None and focused.id in ("queue", "downloads-table"):
            hints = "[b]r[/] retry   [b]c[/] clear finished   [b]h[/] previous pane"
        if hints != self.current_hints:
            self.current_hints = hints
            self.query_one(".hints-context", Static).update(hints)
