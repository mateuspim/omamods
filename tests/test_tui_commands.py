"""Exercise ':' command parsing, matching, and vim motions without a TUI."""

import unittest

from omamods.nexus_api import NexusFile
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.tui.commands import (
    GLOBAL_COMMANDS,
    find_file,
    find_game,
    help_text,
    parse_command,
    resolve_command,
)
from omamods.tui.mods_commands import MODS_COMMANDS
from omamods.tui.vim import ChordTracker, run_motion

ALL = GLOBAL_COMMANDS + MODS_COMMANDS
FILES = (
    NexusFile(1028, "Outfit-100-1-0.rar", "OLD_VERSION", 0, "Outfit", "1.0"),
    NexusFile(3038, "Outfit-100-1-1.rar", "MAIN", 0, "Outfit", "1.1"),
    NexusFile(3039, "OutfitAlt-100-1-1.rar", "MAIN", 0, "OutfitAlt", "1.1"),
)


class FakeList:
    """Record which motion action a widget received."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def action_cursor_down(self) -> None:
        self.calls.append("down")

    def action_scroll_top(self) -> None:
        self.calls.append("top")


class CommandParsingTests(unittest.TestCase):
    def test_parse_handles_colon_quotes_and_blank(self) -> None:
        parsed = parse_command(':install "Sample Outfit"')
        self.assertEqual((parsed.word, parsed.args), ("install", ("Sample Outfit",)))
        self.assertIsNone(parse_command("  "))
        with self.assertRaisesRegex(ValueError, "balanced quotes"):
            parse_command(':add "x')

    def test_uninstall_all_never_shadows_uninstall(self) -> None:
        self.assertEqual(resolve_command("uninstall", ALL).name, "uninstall")
        self.assertEqual(resolve_command("u", ALL).name, "uninstall")
        self.assertEqual(resolve_command("uninstall-", ALL).name, "uninstall-all")
        # A short prefix of the destructive command must not pick one silently.
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            resolve_command("unin", ALL)

    def test_resolve_aliases_prefixes_and_errors(self) -> None:
        self.assertEqual(resolve_command("q", ALL).name, "quit")
        self.assertEqual(resolve_command("inst", ALL).name, "install")
        self.assertEqual(resolve_command("x", ALL).name, "rm")
        with self.assertRaisesRegex(ValueError, "E464: Ambiguous use of :qu"):
            resolve_command("qu", ALL)
        with self.assertRaisesRegex(ValueError, "E492"):
            resolve_command("frobnicate", ALL)

    def test_help_lists_every_command(self) -> None:
        text = help_text(ALL)
        self.assertEqual(len(text.splitlines()), len(ALL))
        self.assertIn(":install [file]", text)


class MatchingTests(unittest.TestCase):
    def test_find_file_by_id_name_and_prefers_current(self) -> None:
        self.assertEqual(find_file(FILES, "1028").file_id, 1028)
        self.assertEqual(find_file(FILES, "outfitalt").file_id, 3039)
        # Regression: mod 365's OLD_VERSION shares MAIN's name.
        self.assertEqual(find_file(FILES, "Outfit").file_id, 3038)
        with self.assertRaisesRegex(ValueError, "expected one match"):
            find_file(FILES, "rar")

    def test_find_game_by_initials_prefix_or_name(self) -> None:
        games = tuple(PAK_OVERLAY_GAMES.values())
        self.assertEqual(find_game(games, "sb").game_id, "stellar-blade")
        self.assertEqual(find_game(games, "cro").game_id, "cronos")
        self.assertEqual(find_game(games, "Blade").game_id, "stellar-blade")
        with self.assertRaisesRegex(ValueError, "expected one of"):
            find_game(games, "skyrim")


class VimTests(unittest.TestCase):
    def test_gg_needs_two_quick_presses(self) -> None:
        chord = ChordTracker()
        self.assertFalse(chord.press(1.0))
        self.assertTrue(chord.press(1.3))
        self.assertFalse(chord.press(5.0))
        self.assertFalse(chord.press(6.0))

    def test_motion_uses_first_supported_action(self) -> None:
        widget = FakeList()
        self.assertTrue(run_motion(widget, "down"))
        self.assertTrue(run_motion(widget, "top"))  # Falls back to scroll_top.
        self.assertFalse(run_motion(widget, "page_up"))
        self.assertEqual(widget.calls, ["down", "top"])


if __name__ == "__main__":
    unittest.main()
