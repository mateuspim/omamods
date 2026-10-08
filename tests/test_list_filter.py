"""Match, mark, and step through '/' filter results."""

import unittest

from omamods.tui.list_filter import (
    MATCH_STYLE,
    mark_matches,
    matches_query,
    query_words,
    search_title,
)
from omamods.tui.list_search import wrapped_step


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
