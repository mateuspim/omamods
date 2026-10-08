"""Show what Steam and the Proton prefix need for RED4ext/CET, ready to copy.

Two separate fixes: the launch options line (DLL overrides) and the prefix's
Visual C++ runtime (an old one makes CET fail with error 998).
"""

from collections.abc import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from omamods.launch_options_advice import LaunchOptionsAdvice
from omamods.proton_runtime import MIN_MSVC_RUNTIME
from omamods.red_frameworks import launch_options_hint

TextCopier = Callable[[str], None]
STEAM_PATH = "Steam → right-click the game → Properties → General → Launch Options."


def _launch_section(advice: LaunchOptionsAdvice) -> str:
    current = advice.current or "(empty)"
    if not advice.missing:
        return f"Steam launch options are fine:\n  {current}"
    return (
        f"Steam has now:\n  {current}\n\nSet it to:\n  {advice.suggested}\n\n"
        f"{launch_options_hint(advice.missing)}\n{STEAM_PATH}"
    )


def _runtime_section(advice: LaunchOptionsAdvice) -> str:
    if advice.runtime_fix is None:
        return ""
    found = ".".join(str(part) for part in (advice.runtime or ())[:3])
    needed = ".".join(str(part) for part in MIN_MSVC_RUNTIME)
    return (
        f"\n\nThe Proton prefix has Visual C++ runtime {found}; RED4ext and CET "
        f"need {needed}+ (otherwise CET fails with error 998).\n"
        f"Close the game, then run:\n  {advice.runtime_fix}"
    )


def launch_options_lines(advice: LaunchOptionsAdvice) -> str:
    """Explain both fixes; e.g. ``Static(launch_options_lines(advice))``."""
    return _launch_section(advice) + _runtime_section(advice)


def launch_options_text(advice: LaunchOptionsAdvice) -> Text:
    """Highlight what to paste or run; e.g. ``Static(launch_options_text(a))``."""
    text = Text(launch_options_lines(advice))
    targets = [advice.suggested] if advice.missing else []
    targets += [advice.runtime_fix] if advice.runtime_fix else []
    text.highlight_words(targets, style="bold green")
    return text


def setup_hint(advice: LaunchOptionsAdvice) -> str:
    """List the copy keys that apply; e.g. ``setup_hint(advice)``."""
    keys = ["c copies the launch options"] if advice.missing else []
    keys += ["p copies the protontricks command"] if advice.runtime_fix else []
    return ", ".join([*keys, "Esc closes"])


class LaunchOptionsDialog(ModalScreen[None]):
    """Offer both fixes; e.g. ``LaunchOptionsDialog(advice, service.copy_to_clipboard)``."""

    BINDINGS = [
        Binding("c", "copy", "Copy launch options"),
        Binding("p", "copy_runtime_fix", "Copy protontricks command"),
        Binding("escape,q,enter", "close", "Close"),
    ]

    def __init__(self, advice: LaunchOptionsAdvice, copier: TextCopier) -> None:
        super().__init__()
        self.advice = advice
        self.copier = copier

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog large"):
            yield Label("Steam and Proton setup", classes="dialog-title")
            yield Static(launch_options_text(self.advice))
            yield Static(setup_hint(self.advice), classes="hint")

    def action_copy(self) -> None:
        copy_launch_line(self, self.advice, self.copier)

    def action_copy_runtime_fix(self) -> None:
        copy_runtime_fix(self, self.advice, self.copier)

    def action_close(self) -> None:
        self.dismiss(None)


def _copy(screen: ModalScreen[object], text: str, copier: TextCopier) -> None:
    # OSC 52 covers terminals and hosts without wl-copy.
    screen.app.copy_to_clipboard(text)
    try:
        copier(text)
    except ValueError:
        pass  # wl-copy missing; the terminal copy above still ran.


def copy_launch_line(
    screen: ModalScreen[object], advice: LaunchOptionsAdvice, copier: TextCopier
) -> None:
    """Copy the merged line; e.g. ``copy_launch_line(self, advice, copy)``."""
    if not advice.missing:
        return
    _copy(screen, advice.suggested, copier)
    screen.notify("Copied; paste it into Steam's Launch Options.")


def copy_runtime_fix(
    screen: ModalScreen[object], advice: LaunchOptionsAdvice, copier: TextCopier
) -> None:
    """Copy the protontricks command; e.g. ``copy_runtime_fix(self, advice, copy)``."""
    if advice.runtime_fix is None:
        return
    _copy(screen, advice.runtime_fix, copier)
    screen.notify("Copied; close the game, then run it in a terminal.")
