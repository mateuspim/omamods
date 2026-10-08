"""Show Steam's launch options next to the line to paste, ready to copy."""

from collections.abc import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from omamods.launch_options_advice import LaunchOptionsAdvice
from omamods.red_frameworks import launch_options_hint

TextCopier = Callable[[str], None]


def launch_options_lines(advice: LaunchOptionsAdvice) -> str:
    """Explain the change; e.g. ``Static(launch_options_lines(advice))``."""
    if not advice.needed:
        return f"Steam has: {advice.current or '(empty)'}\nNothing to add."
    return (
        f"Steam has now:\n  {advice.current or '(empty)'}\n\n"
        f"Set it to:\n  {advice.suggested}\n\n"
        f"{launch_options_hint(advice.missing)}\n"
        "Steam → right-click the game → Properties → General → Launch Options."
    )


def launch_options_text(advice: LaunchOptionsAdvice) -> Text:
    """Highlight the line to paste; e.g. ``Static(launch_options_text(advice))``."""
    text = Text(launch_options_lines(advice))
    if advice.needed:
        text.highlight_words([advice.suggested], style="bold green")
    return text


class LaunchOptionsDialog(ModalScreen[None]):
    """Offer the fixed line; e.g. ``LaunchOptionsDialog(advice, service.copy_to_clipboard)``."""

    BINDINGS = [
        Binding("c", "copy", "Copy line"),
        Binding("escape,q,enter", "close", "Close"),
    ]

    def __init__(self, advice: LaunchOptionsAdvice, copier: TextCopier) -> None:
        super().__init__()
        self.advice = advice
        self.copier = copier

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog large"):
            yield Label("Steam launch options", classes="dialog-title")
            yield Static(launch_options_text(self.advice))
            hint = (
                "c copies the new line, Esc closes"
                if self.advice.needed
                else "Esc closes"
            )
            yield Static(hint, classes="hint")

    def action_copy(self) -> None:
        copy_launch_line(self, self.advice, self.copier)

    def action_close(self) -> None:
        self.dismiss(None)


def copy_launch_line(
    screen: ModalScreen[object], advice: LaunchOptionsAdvice, copier: TextCopier
) -> None:
    """Copy through wl-copy and the terminal; e.g. ``copy_launch_line(self, a, copy)``."""
    if not advice.needed:
        return
    # OSC 52 covers terminals and hosts without wl-copy.
    screen.app.copy_to_clipboard(advice.suggested)
    try:
        copier(advice.suggested)
    except ValueError:
        pass  # wl-copy missing; the terminal copy above still ran.
    screen.notify("Copied; paste it into Steam's Launch Options.")
