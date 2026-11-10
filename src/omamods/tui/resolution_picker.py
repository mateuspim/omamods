"""Pick a display resolution from a list, monitors first, or type another."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from omamods.display_sizes import SizeChoice

OTHER_SIZE = "other"


def first_allowed(choices: tuple[SizeChoice, ...]) -> str:
    """The size to suggest; e.g. ``first_allowed(choices) == '3440x1440'``."""
    return next((choice.size for choice in choices if choice.allowed), "")


class ResolutionPicker(ModalScreen[str | None]):
    """Return ``WIDTHxHEIGHT``, ``OTHER_SIZE``, or None; e.g. ``ResolutionPicker(t, choices)``."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, choices: tuple[SizeChoice, ...]) -> None:
        super().__init__()
        self.title_text = title
        self.choices = choices

    def compose(self) -> ComposeResult:
        options = [
            Option(choice.label, id=choice.size, disabled=not choice.allowed)
            for choice in self.choices
        ]
        options.append(Option("Other size…", id=OTHER_SIZE))
        with Vertical(classes="dialog wide"):
            yield Label(self.title_text, classes="dialog-title")
            yield OptionList(*options, id="sizes")
            yield Static("Enter to choose, Esc to cancel", classes="hint")

    def on_mount(self) -> None:
        sizes = self.query_one("#sizes", OptionList)
        suggested = first_allowed(self.choices) or OTHER_SIZE
        sizes.highlighted = sizes.get_option_index(suggested)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
