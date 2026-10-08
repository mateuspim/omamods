"""Match, mark, and step through '/' filter results."""

import unittest

from omamods.staging import StagedMod
from omamods.tui.command_bar import match_hint
from omamods.tui.list_filter import (
    MATCH_STYLE,
    mark_matches,
    matches_query,
    no_match_option,
    query_words,
    search_title,
)
from omamods.tui.list_search import wrapped_step
from omamods.tui.mod_rows import INSTALLED_MARK, STAGED_MARK, mod_mark


class ListFilterTests(unittest.TestCase):
    def test_query_words_lowercase_and_split(self) -> None:
        self.assertEqual(query_words("  Blue  SUIT "), ("blue", "suit"))
        self.assertEqual(query_words(""), ())

    def test_every_word_must_appear_in_any_order(self) -> None:
        self.assertTrue(matches_query("Hair Pack", "pa HA"))
        self.assertFalse(matches_query("Hair Pack", "hair suit"))
        self.assertTrue(matches_query("Anything", ""))

    def test_marks_each_occurrence(self) -> None:
        text = mark_matches("Hair hair Pack", "HAIR")
        spans = [(s.start, s.end) for s in text.spans if s.style == MATCH_STYLE]
        self.assertEqual(spans, [(0, 4), (5, 9)])
        self.assertEqual(text.plain, "Hair hair Pack")

    def test_mark_offsets_survive_sharp_s(self) -> None:
        # casefold() would turn ß into ss and shift every later span by one.
        text = mark_matches("Straße Blade", "blade")
        self.assertEqual([(s.start, s.end) for s in text.spans], [(7, 12)])

    def test_title_shows_query_and_counts(self) -> None:
        self.assertEqual(search_title("Mods", "", 3, 3), "Mods")
        self.assertEqual(search_title("Mods", "hair", 2, 9), "Mods · /hair (2/9)")

    def test_no_match_option_names_the_query_and_cannot_be_picked(self) -> None:
        option = no_match_option("zz")
        self.assertTrue(option.disabled)
        self.assertEqual(str(option.prompt), "No matches for /zz")

    def test_match_hint_counts_matches(self) -> None:
        self.assertTrue(match_hint(0).startswith("no matches"))
        self.assertTrue(match_hint(1).startswith("1 match ·"))
        self.assertTrue(match_hint(2).startswith("2 matches ·"))


class ModRowTests(unittest.TestCase):
    def _mod(self, installed: frozenset[int]) -> StagedMod:
        return StagedMod(1, None, (), {}, None, installed)

    def test_marks_mods_with_installed_files(self) -> None:
        self.assertEqual(mod_mark(self._mod(frozenset({5}))), INSTALLED_MARK)
        self.assertEqual(mod_mark(self._mod(frozenset())), STAGED_MARK)


class WrappedStepTests(unittest.TestCase):
    def test_moves_forward_and_wraps(self) -> None:
        self.assertEqual(wrapped_step([1, 3, 5], 1, 1), 3)
        self.assertEqual(wrapped_step([1, 3, 5], 5, 1), 1)

    def test_moves_backward_and_wraps(self) -> None:
        self.assertEqual(wrapped_step([1, 3, 5], 3, -1), 1)
        self.assertEqual(wrapped_step([1, 3, 5], 1, -1), 5)

    def test_starts_at_an_end_without_a_highlight(self) -> None:
        self.assertEqual(wrapped_step([2, 4], None, 1), 2)
        self.assertEqual(wrapped_step([2, 4], None, -1), 4)


if __name__ == "__main__":
    unittest.main()
