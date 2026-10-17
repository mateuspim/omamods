"""Merge the DLL overrides into a game's existing Steam launch options."""

import unittest

from omamods.launch_options_advice import (
    launch_options_advice,
    merged_launch_options,
)
from omamods.red_frameworks import CET_MOD_ID, RED4EXT_MOD_ID
from omamods.tui.launch_options_dialog import launch_options_text, setup_hint

BOTH = ("version", "winmm")
HDR = "PROTON_ENABLE_WAYLAND=1 PROTON_ENABLE_HDR=1 %command%"


class MergeTests(unittest.TestCase):
    def test_keeps_existing_variables(self) -> None:
        self.assertEqual(
            merged_launch_options(HDR, BOTH),
            f'WINEDLLOVERRIDES="version,winmm=n,b" {HDR}',
        )

    def test_empty_options_get_command(self) -> None:
        self.assertEqual(
            merged_launch_options("", BOTH),
            'WINEDLLOVERRIDES="version,winmm=n,b" %command%',
        )

    def test_bare_game_arguments_stay_arguments(self) -> None:
        self.assertEqual(
            merged_launch_options("-skipStartScreen", ("winmm",)),
            'WINEDLLOVERRIDES="winmm=n,b" %command% -skipStartScreen',
        )

    def test_existing_overrides_are_extended(self) -> None:
        self.assertEqual(
            merged_launch_options('WINEDLLOVERRIDES="dxgi=n,b" %command%', BOTH),
            'WINEDLLOVERRIDES="dxgi=n,b;version,winmm=n,b" %command%',
        )

    def test_nothing_missing_changes_nothing(self) -> None:
        self.assertEqual(merged_launch_options(HDR, ()), HDR)


class AdviceTests(unittest.TestCase):
    def test_advice_for_installed_frameworks(self) -> None:
        advice = launch_options_advice((HDR,), frozenset({RED4EXT_MOD_ID, CET_MOD_ID}))
        self.assertTrue(advice.needed)
        self.assertEqual(advice.missing, BOTH)
        self.assertEqual(advice.current, HDR)

    def test_fixed_line_needs_nothing(self) -> None:
        fixed = f'WINEDLLOVERRIDES="version,winmm=n,b" {HDR}'
        advice = launch_options_advice((fixed,), frozenset({RED4EXT_MOD_ID}))
        self.assertFalse(advice.needed)
        self.assertEqual(advice.suggested, fixed)

    def test_no_steam_options_reads_as_empty(self) -> None:
        advice = launch_options_advice((), frozenset({CET_MOD_ID}))
        self.assertEqual(advice.current, "")
        self.assertEqual(advice.suggested, 'WINEDLLOVERRIDES="version=n,b" %command%')


class DialogTextTests(unittest.TestCase):
    def test_line_to_paste_is_highlighted(self) -> None:
        advice = launch_options_advice((HDR,), frozenset({RED4EXT_MOD_ID}))
        text = launch_options_text(advice)
        start = text.plain.index(advice.suggested)
        styles = [span.style for span in text.spans if span.start == start]
        self.assertEqual(styles, ["bold green"])

    def test_fixed_line_says_nothing_to_add(self) -> None:
        fixed = f'WINEDLLOVERRIDES="winmm=n,b" {HDR}'
        advice = launch_options_advice((fixed,), frozenset({RED4EXT_MOD_ID}))
        self.assertIn("launch options are fine", launch_options_text(advice).plain)

    def test_runtime_section_highlights_the_command(self) -> None:
        ids = frozenset({RED4EXT_MOD_ID})
        advice = launch_options_advice((HDR,), ids, (14, 28, 29334, 0), "1091500")
        text = launch_options_text(advice)
        self.assertIn("Visual C++ runtime 14.28.29334", text.plain)
        start = text.plain.index("protontricks 1091500 -q vcrun2022")
        self.assertIn("bold green", [s.style for s in text.spans if s.start == start])
        self.assertEqual(
            setup_hint(advice),
            "w saves the launch options to Steam, c copies them, "
            "p copies the protontricks command, Esc closes",
        )


if __name__ == "__main__":
    unittest.main()
