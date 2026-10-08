"""Ask for the AyakaMods login cookie, filling it in from the clipboard.

The user copies ``xf_user`` in the browser's DevTools; the dialog checks the
clipboard every second and fills the field once a cookie-shaped value shows
up, so the only step left in the terminal is Enter.
"""

from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

CLIPBOARD_POLL_SECONDS = 1.0
LOGIN_STEPS = (
    "1. Log in on the AyakaMods page that just opened (tick 'Stay logged in').\n"
    "2. Press F12 > Application > Cookies > https://ayakamods.com.\n"
    "3. Copy the value of xf_user; it appears here by itself.\n"
    "Enter saves it and downloads; Esc downloads in the browser instead."
)
# Returns a cookie-shaped clipboard value, or None.
ClipboardCookie = Callable[[], str | None]


class LoginCookiePrompt(ModalScreen[str | None]):
    """Collect the xf_user cookie; e.g. ``LoginCookiePrompt('Expired', reader)``."""

    BINDINGS = [Binding("escape", "cancel", "Use the browser")]

    def __init__(self, reason: str, clipboard_cookie: ClipboardCookie) -> None:
        super().__init__()
        self.reason = reason
        self.clipboard_cookie = clipboard_cookie

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label(
                f"AyakaMods login needed: {self.reason}", classes="dialog-title"
            )
            yield Static(LOGIN_STEPS, markup=False)
            yield Input(
                placeholder="xf_user value, e.g. 347376%2CAbC...", password=True
            )
            yield Static("Waiting for the clipboard...", id="clipboard", classes="hint")

    def on_mount(self) -> None:
        self.query_one(Input).focus()
        self.set_interval(CLIPBOARD_POLL_SECONDS, self.check_clipboard)

    def check_clipboard(self) -> None:
        """Fill the field from a copied cookie; runs on a timer."""
        field = self.query_one(Input)
        if field.value:
            return
        cookie = self.clipboard_cookie()
        if cookie is None:
            return
        field.value = cookie
        self.query_one("#clipboard", Static).update(
            "Found a login cookie on the clipboard; press Enter to save it."
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
