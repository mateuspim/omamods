"""Translate an Omarchy palette into Textual and Rich colour systems."""

from rich.terminal_theme import TerminalTheme
from textual.color import Color
from textual.theme import Theme

from omamods.omarchy_palette import OmarchyPalette

ANSI_COLOURS = (
    "dark_background",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "foreground",
)


def workspace_theme(palette: OmarchyPalette) -> Theme:
    """Keep every UI surface in the desktop palette; e.g. ``workspace_theme(nord)``."""
    foreground = palette.colour("foreground")
    background = palette.colour("background")
    accent = palette.colour("accent")
    return Theme(
        name="omarchy",
        dark=palette.dark,
        primary=accent,
        accent=accent,
        secondary=palette.colour("cyan", accent),
        foreground=foreground,
        background=palette.colour("dark_background", background),
        surface=background,
        panel=palette.colour("selection", _blend(background, foreground, 0.12)),
        success=palette.colour("green", accent),
        warning=palette.colour("yellow", accent),
        error=palette.colour("red", accent),
        variables=_workspace_variables(palette),
    )


def _workspace_variables(palette: OmarchyPalette) -> dict[str, str]:
    background, foreground = palette.colour("background"), palette.colour("foreground")
    return {
        "text-muted": palette.colour(
            "light_foreground", _blend(background, foreground, 0.65)
        ),
        "border": _blend(background, foreground, 0.25),
    }


def _blend(first: str, second: str, fraction: float) -> str:
    return Color.parse(first).blend(Color.parse(second), fraction).hex


def terminal_theme(palette: OmarchyPalette) -> TerminalTheme:
    """Map semantic Rich colours to Omarchy too; e.g. ``terminal_theme(nord)``."""
    background = palette.colour("background")
    foreground = palette.colour("foreground")
    normal = [_rgb(palette.colour(name, foreground)) for name in ANSI_COLOURS]
    bright = [
        _rgb(palette.colour(f"bright_{name}", palette.colour(name, foreground)))
        for name in ANSI_COLOURS
    ]
    # Staged-only markers use bright black; mapping it to the background hides them.
    bright[0] = _rgb(
        palette.colour("dark_foreground", _blend(background, foreground, 0.5))
    )
    return TerminalTheme(_rgb(background), _rgb(foreground), normal, bright)


def _rgb(value: str) -> tuple[int, int, int]:
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
