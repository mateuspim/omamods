"""Show a mod's main picture inline, behind a widget this project owns.

textual-image picks the best protocol the terminal supports: Kitty graphics
(Kitty, Ghostty), Sixel (foot), or coloured half-blocks (e.g. Alacritty), so
the full-quality image is always one key away in imv.
"""

from pathlib import Path

from PIL import Image as PilImage
from PIL import ImageFilter
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static
from textual_image.widget import Image

# Shrinking first makes the blur fast on big screenshots and strong enough
# that nothing shows through, whatever the original size.
BLUR_WIDTH = 160
BLUR_RADIUS = 8
BLUR_NOTE = "18+ · picture blurred · H cycles blur, hide, show · o opens it"
EMPTY_ARTWORK = "[b]◇[/]\n\nNo artwork cached\n[dim]A mod's picture appears here[/]"


def blurred_picture(picture: Path) -> PilImage.Image:
    """Load picture heavily blurred; e.g. ``Image(blurred_picture(path))``."""
    with PilImage.open(picture) as original:
        small = original.convert("RGB")
    small.thumbnail((BLUR_WIDTH, BLUR_WIDTH))
    return small.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))


class PicturePreview(Container):
    """Swap between a picture and a placeholder; e.g. ``preview.show(path)``."""

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        # What is on screen, so re-showing it does not flicker or re-blur.
        self.showing: tuple[Path | None, bool] = (None, False)

    def compose(self) -> ComposeResult:
        yield Static(EMPTY_ARTWORK, classes="placeholder")

    def show(self, picture: Path | None, blurred: bool = False) -> None:
        """Display ``picture`` (blurred or not) or the placeholder; e.g. ``preview.show(None)``."""
        if (picture, blurred) == self.showing:
            return
        self.showing = (picture, blurred)
        self.remove_children()
        if picture is None:
            self.mount(Static(EMPTY_ARTWORK, classes="placeholder"))
            return
        if not blurred:
            self.mount(Image(str(picture), on_error=self._unreadable))
            return
        self._show_blurred(picture)

    def _show_blurred(self, picture: Path) -> None:
        try:
            image = blurred_picture(picture)
        except (OSError, ValueError) as error:
            self.mount(self._unreadable(error))
            return
        self.mount(Static(BLUR_NOTE, classes="nsfw-note"), Image(image))

    def _unreadable(self, error: Exception) -> Static:
        return Static(f"Picture unreadable: {error}", classes="placeholder")
