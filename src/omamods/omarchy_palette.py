"""Read Omarchy's staged colour palette without changing desktop configuration."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import Protocol

from omamods.filesystem import ReadableFiles

COLOUR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}\Z")
NUMBERED_COLOURS = (
    "dark_background",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "foreground",
    "dark_foreground",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_foreground",
)
PALETTE_COLOURS = (
    frozenset(NUMBERED_COLOURS)
    | {
        "background",
        "accent",
        "selection",
        "muted",
        "darker_background",
        "lighter_background",
        "light_foreground",
        "orange",
        "brown",
    }
    | {f"color{index}" for index in range(16)}
)


@dataclass(frozen=True)
class OmarchyPalette:
    """A validated colour-only snapshot; e.g. ``palette.colour('accent')``."""

    name: str
    dark: bool
    colours: tuple[tuple[str, str], ...]

    def colour(self, key: str, fallback: str | None = None) -> str:
        """Look up a theme colour; e.g. ``palette.colour('cyan', '#88c0d0')``."""
        value = dict(self.colours).get(key, fallback)
        if value is None:
            raise ValueError(f"colour={key!r}: expected a defined palette colour")
        return value


class PaletteReader(Protocol):
    """Expose read-only theme snapshots; e.g. ``reader.read()``."""

    def read(self) -> OmarchyPalette | None:
        """Read a palette, or None when absent; e.g. ``reader.read()``."""
        ...


def parse_omarchy_palette(source: str, name: str) -> OmarchyPalette:
    """Read palette tokens from TOML; e.g. ``parse_omarchy_palette(text, 'Nord')``."""
    fields = tomllib.loads(source)
    missing = {"background", "foreground", "accent"} - fields.keys()
    if missing:
        raise ValueError(f"palette={name!r}: expected colours {sorted(missing)!r}")
    mode = fields.pop("mode", "dark")
    if mode not in ("dark", "light"):
        raise ValueError(f"mode={mode!r}: expected 'dark' or 'light'")
    colours = tuple(sorted(_palette_colours(fields).items()))
    return OmarchyPalette(name, mode == "dark", colours)


def _palette_colours(fields: Mapping[str, object]) -> dict[str, str]:
    # Community themes also store opacity, border gradients, and extension tables.
    colours = {
        key: _valid_colour(key, value)
        for key, value in fields.items()
        if key in PALETTE_COLOURS
    }
    for index, name in enumerate(NUMBERED_COLOURS):
        if f"color{index}" in colours:
            colours.setdefault(name, colours[f"color{index}"])
    return colours


def _valid_colour(key: str, value: object) -> str:
    if not isinstance(value, str) or not COLOUR_PATTERN.fullmatch(value):
        raise ValueError(f"colour {key}={value!r}: expected '#RRGGBB'")
    return value.lower()


def omarchy_palette_paths(
    home: Path, environment: Mapping[str, str]
) -> tuple[Path, ...]:
    """Locate staged palettes across releases; e.g. ``omarchy_palette_paths(home, env)``."""
    state = Path(environment.get("XDG_STATE_HOME", str(home / ".local/state")))
    config = Path(environment.get("XDG_CONFIG_HOME", str(home / ".config")))
    roots = (home / ".local/state", state, config)
    return tuple(
        dict.fromkeys(root / "omarchy/current/theme/colors.toml" for root in roots)
    )


class OmarchyPaletteReader:
    """Follow staged palette replacement; e.g. ``OmarchyPaletteReader(paths, files)``."""

    def __init__(self, paths: tuple[Path, ...], files: ReadableFiles) -> None:
        self.paths = paths
        self.files = files

    def read(self) -> OmarchyPalette | None:
        """Reopen the current path each time; e.g. ``reader.read()``."""
        for path in self.paths:
            try:
                source = self.files.read_text(path)
            except FileNotFoundError:
                continue
            return parse_omarchy_palette(source, self._theme_name(path))
        return None

    def _theme_name(self, path: Path) -> str:
        try:
            return (
                self.files.read_text(path.parent.parent / "theme.name").strip()
                or "Omarchy"
            )
        except FileNotFoundError:
            return "Omarchy"
