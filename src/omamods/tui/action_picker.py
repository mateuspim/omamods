"""A searchable action picker backed by the same commands as the ':' line."""

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from omamods.tui.commands import CommandSpec


def matching_actions(
    commands: tuple[CommandSpec, ...], query: str
) -> tuple[CommandSpec, ...]:
    """Match words in names and descriptions; e.g. ``matching_actions(specs, 'mod')``."""
    words = query.casefold().split()
    return tuple(
        spec
        for spec in commands
        if all(word in f"{spec.name} {spec.summary}".casefold() for word in words)
    )


class ActionPicker(ModalScreen[str | None]):
    """Find an action without remembering keys; e.g. ``ActionPicker(commands)``."""

    BINDINGS = [
        Binding("escape", "cancel", show=False),
        Binding("down,ctrl+j", "move(1)", show=False, priority=True),
        Binding("up,ctrl+k", "move(-1)", show=False, priority=True),
    ]

    def __init__(self, commands: tuple[CommandSpec, ...]) -> None:
        super().__init__()
        self.commands = tuple(
            sorted(
                commands, key=lambda spec: (spec.name in ("quit", "quitall"), spec.name)
            )
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="action-picker"):
            yield Static("◈  ACTIONS", classes="dialog-title")
            yield Input(placeholder="Find an action…", id="action-query")
            yield OptionList(id="action-results")
            yield Static("↑ ↓ navigate   enter select   esc close", classes="hint")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._fill_actions(event.value)

    def on_mount(self) -> None:
        self._fill_actions("")

    def _fill_actions(self, query: str) -> None:
        matches = matching_actions(self.commands, query)
        rows = self.query_one("#action-results", OptionList)
        rows.clear_options()
        for spec in matches:
            label = Text.assemble(
                (f":{spec.name:<17} ", "bold cyan"), (spec.summary, "dim")
            )
            rows.add_option(Option(label, id=spec.name))
        if not matches:
            rows.add_option(
                Option("No actions match. Try another word.", disabled=True)
            )
        rows.highlighted = 0

    def on_input_submitted(self, event: Input.Submitted) -> None:
        option = self.query_one("#action-results", OptionList).highlighted_option
        if option is not None and not option.disabled:
            self.dismiss(option.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_move(self, step: int) -> None:
        """Navigate while keeping the query focused; e.g. ``picker.action_move(1)``."""
        rows = self.query_one("#action-results", OptionList)
        if step > 0:
            rows.action_cursor_down()
        else:
            rows.action_cursor_up()

    def action_cancel(self) -> None:
        self.dismiss(None)
