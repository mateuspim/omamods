"""Show a mod's main picture inline, behind a widget this project owns.

textual-image picks the best protocol the terminal supports: Kitty graphics
(Kitty, Ghostty), Sixel (foot), or coloured half-blocks (e.g. Alacritty), so
the full-quality image is always one key away in imv.
"""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static
from textual_image.widget import Image


class PicturePreview(Container):
    """Swap between a picture and a placeholder; e.g. ``preview.show(path)``."""

    def compose(self) -> ComposeResult:
        yield Static("No picture", classes="placeholder")

    def show(self, picture: Path | None) -> None:
        """Display ``picture`` or the placeholder; e.g. ``preview.show(None)``."""
        self.remove_children()
        if picture is None:
            self.mount(Static("No picture", classes="placeholder"))
            return
        self.mount(Image(str(picture), on_error=self._unreadable))

    def _unreadable(self, error: Exception) -> Static:
        return Static(f"Picture unreadable: {error}", classes="placeholder")
