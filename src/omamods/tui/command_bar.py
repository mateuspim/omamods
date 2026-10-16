"""Vim's bottom line: the ':' command prompt and the '/' filter prompt."""

from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.suggester import Suggester, SuggestFromList
from textual.widgets import Input, Label

COMMAND_HINT = "Tab completes · Enter runs · Esc cancels"
SEARCH_HINT = "Enter keeps · Esc cancels"


def bottom_line(prefix: str, field: Input, hint: str) -> ComposeResult:
    """Lay out prefix, input, and hint on one row; e.g. ``yield from bottom_line(...)``."""
    with Horizontal(id="command-bar"):
        yield Label(prefix, id="command-prefix")
        yield field
        yield Label(hint, id="command-hint")


def match_hint(shown: int) -> str:
    """Count live matches for the '/' line; e.g. ``match_hint(2) == '2 matches · ...'``."""
    if shown == 0:
        return f"no matches · {SEARCH_HINT}"
    noun = "match" if shown == 1 else "matches"
    return f"{shown} {noun} · {SEARCH_HINT}"


class CommandPrompt(ModalScreen[str | None]):
    """A one-line ':' prompt at the bottom, like vim's command line."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, prefix: str, words: tuple[str, ...], initial: str = "") -> None:
        super().__init__(classes="command-screen")
        self.prefix = prefix
        self.words = words
        self.initial = initial

    def compose(self) -> ComposeResult:
        suggester: Suggester | None = (
            SuggestFromList(self.words, case_sensitive=False) if self.words else None
        )
        field = Input(
            self.initial, id="command-line", suggester=suggester, select_on_focus=False
        )
        yield from bottom_line(self.prefix, field, COMMAND_HINT)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SearchPrompt(ModalScreen[str | None]):
    """A '/' line that filters the list below as you type; Enter keeps, Esc restores."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, query: str, on_change: Callable[[str], int]) -> None:
        super().__init__(classes="command-screen")
        self.query_text = query
        self.on_change = on_change

    def compose(self) -> ComposeResult:
        field = Input(self.query_text, id="command-line")
        yield from bottom_line("/", field, SEARCH_HINT)

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        shown = self.on_change(query)
        hint = self.query_one("#command-hint", Label)
        hint.update(match_hint(shown) if query else SEARCH_HINT)
        hint.set_class(bool(query) and shown == 0, "no-matches")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)
