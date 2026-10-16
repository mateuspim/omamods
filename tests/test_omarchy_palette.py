"""Validate desktop palette parsing, location discovery, and replacement reads."""

from pathlib import Path
import unittest

from omamods.omarchy_palette import (
    OmarchyPaletteReader,
    omarchy_palette_paths,
    parse_omarchy_palette,
)
from omamods.tui.theme_bridge import terminal_theme, workspace_theme
from tests.fakes import FakeFiles

NORD_COLOURS = """
mode = "dark"
background = "#2e3440"
foreground = "#d8dee9"
accent = "#81a1c1"
dark_background = "#222730"
selection = "#434c5e"
light_foreground = "#adb5c4"
red = "#bf616a"
green = "#a3be8c"
yellow = "#ebcb8b"
blue = "#81a1c1"
magenta = "#b48ead"
cyan = "#88c0d0"
"""
LIGHT_COLOURS = """
mode = "light"
background = "#fafafa"
foreground = "#303030"
accent = "#0055aa"
"""
LIFELESS_COLOURS = """
mode = "dark"
accent = "#abfeff"
background = "#243031"
foreground = "#dcd6ce"
cyan = "#77e0f8"
terminal_opacity = 0.82
terminal_blur = true
terminal_blur_radius = 28
hyprland_active_border = "#7EC2B2 #294842 45deg"
hyprland_inactive_border = "#2c3547"
[extension]
enabled = true
"""


class PaletteParsingTests(unittest.TestCase):
    def test_community_theme_settings_do_not_invalidate_palette(self) -> None:
        palette = parse_omarchy_palette(LIFELESS_COLOURS, "Lifeless")
        self.assertEqual(palette.colour("accent"), "#abfeff")
        self.assertEqual(palette.colour("background"), "#243031")
        self.assertEqual(terminal_theme(palette).ansi_colors[6], (119, 224, 248))
        self.assertNotIn("terminal_opacity", dict(palette.colours))
        self.assertNotIn("extension", dict(palette.colours))
        self.assertEqual(
            palette,
            parse_omarchy_palette(LIFELESS_COLOURS.replace("0.82", "0.9"), "Lifeless"),
        )

    def test_numbered_palette_maps_normal_and_bright_colours(self) -> None:
        source = (
            LIGHT_COLOURS
            + "\n"
            + "\n".join(f'color{index} = "#{index:02x}2233"' for index in range(16))
        )
        palette = parse_omarchy_palette(source, "Generated")
        ansi = terminal_theme(palette)
        self.assertEqual(tuple(ansi.ansi_colors[0]), (0, 34, 51))
        self.assertEqual(tuple(ansi.ansi_colors[6]), (6, 34, 51))
        self.assertEqual(tuple(ansi.ansi_colors[8]), (8, 34, 51))
        self.assertEqual(tuple(ansi.ansi_colors[14]), (14, 34, 51))
        self.assertEqual(tuple(ansi.ansi_colors[15]), (15, 34, 51))
        self.assertEqual(palette.colour("foreground"), "#303030")
        self.assertEqual(workspace_theme(palette).success, "#022233")

    def test_named_colours_take_precedence_over_numbered_aliases(self) -> None:
        palette = parse_omarchy_palette(NORD_COLOURS + '\ncolor6 = "#123456"', "Mixed")
        self.assertEqual(palette.colour("cyan"), "#88c0d0")

    def test_accepts_light_dark_and_uppercase_colours(self) -> None:
        nord = parse_omarchy_palette(NORD_COLOURS.replace("#81a1c1", "#81A1C1"), "Nord")
        self.assertEqual(nord.colour("accent"), "#81a1c1")
        self.assertTrue(nord.dark)
        light = parse_omarchy_palette(LIGHT_COLOURS, "Light")
        self.assertFalse(light.dark)
        self.assertEqual(light.colour("cyan", "#123456"), "#123456")
        with self.assertRaisesRegex(ValueError, "colour='missing'.*expected"):
            light.colour("missing")

    def test_rejects_incomplete_malformed_and_executable_colour_values(self) -> None:
        for source in (
            'background = "#222222"',
            NORD_COLOURS.replace('"dark"', '"unknown"'),
            NORD_COLOURS.replace('"#81a1c1"', '"$(touch /tmp/no)"'),
            NORD_COLOURS.replace('"#2e3440"', "42"),
            "background = [",
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_omarchy_palette(source, "invalid")

    def test_bridge_maps_surfaces_and_semantic_terminal_colours(self) -> None:
        nord = parse_omarchy_palette(NORD_COLOURS, "Nord")
        theme = workspace_theme(nord)
        self.assertEqual(theme.primary, "#81a1c1")
        self.assertEqual(theme.background, "#222730")
        self.assertEqual(theme.surface, "#2e3440")
        self.assertEqual(theme.variables["text-muted"], "#adb5c4")
        ansi = terminal_theme(nord)
        self.assertEqual(tuple(ansi.ansi_colors[2]), (163, 190, 140))
        self.assertNotEqual(ansi.ansi_colors[8], ansi.background_color)
        light = workspace_theme(parse_omarchy_palette(LIGHT_COLOURS, "Light"))
        self.assertFalse(light.dark)
        self.assertTrue(light.variables["border"].startswith("#"))


class PaletteReadingTests(unittest.TestCase):
    def test_paths_cover_current_and_legacy_locations_without_duplicates(self) -> None:
        home = Path("/home/test")
        paths = omarchy_palette_paths(home, {})
        self.assertEqual(
            paths,
            (
                home / ".local/state/omarchy/current/theme/colors.toml",
                home / ".config/omarchy/current/theme/colors.toml",
            ),
        )
        custom = omarchy_palette_paths(
            home, {"XDG_STATE_HOME": "/state", "XDG_CONFIG_HOME": "/config"}
        )
        self.assertIn(Path("/state/omarchy/current/theme/colors.toml"), custom)
        self.assertIn(Path("/config/omarchy/current/theme/colors.toml"), custom)

    def test_missing_theme_falls_back_and_current_path_is_reopened(self) -> None:
        paths = omarchy_palette_paths(Path("/home/test"), {})
        files = FakeFiles()
        reader = OmarchyPaletteReader(paths, files)
        self.assertIsNone(reader.read())
        files.contents[paths[1]] = NORD_COLOURS
        self.assertEqual(reader.read().name, "Omarchy")
        files.contents[paths[0]] = LIGHT_COLOURS
        files.contents[paths[0].parent.parent / "theme.name"] = "Light\n"
        self.assertEqual(reader.read().name, "Light")
        self.assertFalse(reader.read().dark)
        files.contents[paths[0]] = NORD_COLOURS
        self.assertTrue(reader.read().dark)

    def test_unreadable_palette_is_reported_to_the_app_boundary(self) -> None:
        path = Path("/theme/colors.toml")
        reader = OmarchyPaletteReader(
            (path,), FakeFiles(failures={path: PermissionError("blocked")})
        )
        with self.assertRaises(PermissionError):
            reader.read()
