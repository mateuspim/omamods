"""Exercise stepping a Nexus window through a mod's files."""

import unittest

from omamods.browser_queue import FINISHED, NEXT, STAY, BrowserQueue


class BrowserQueueTests(unittest.TestCase):
    def test_only_first_file_opens_and_duplicates_are_ignored(self) -> None:
        queue = BrowserQueue()
        self.assertTrue(queue.add("sb", 1, 7, "u7"))
        self.assertFalse(queue.add("sb", 1, 8, "u8"))
        self.assertFalse(queue.add("sb", 1, 7, "u7"))
        self.assertTrue(queue.add("sb", 2, 9, "u9"))  # Other mods get a window.

    def test_waiting_url_and_files_follow_the_first_file(self) -> None:
        queue = BrowserQueue()
        self.assertIsNone(queue.waiting_url("sb", 1))
        queue.add("sb", 1, 7, "u7")
        queue.add("sb", 1, 8, "u8")
        queue.add("sb", 2, 9, "u9")
        self.assertEqual(queue.waiting_url("sb", 1), "u7")
        self.assertEqual(queue.waiting_files(), {("sb", 1): 7, ("sb", 2): 9})
        queue.advance("sb", 1, {7})
        self.assertEqual(queue.waiting_url("sb", 1), "u8")

    def test_steps_to_next_file_then_finishes(self) -> None:
        queue = BrowserQueue()
        queue.add("sb", 1, 7, "u7")
        queue.add("sb", 1, 8, "u8")
        self.assertEqual(queue.advance("sb", 1, set()).action, STAY)
        step = queue.advance("sb", 1, {7})
        self.assertEqual((step.action, step.url), (NEXT, "u8"))
        self.assertEqual(queue.advance("sb", 1, {7, 8}).action, FINISHED)
        self.assertEqual(queue.pending, {})

    def test_later_file_arriving_first_keeps_window(self) -> None:
        queue = BrowserQueue()
        queue.add("sb", 1, 7, "u7")
        queue.add("sb", 1, 8, "u8")
        self.assertEqual(queue.advance("sb", 1, {8}).action, STAY)
        self.assertEqual(queue.pending[("sb", 1)], [(7, "u7")])

    def test_unrequested_arrival_is_reported_once(self) -> None:
        # Regression: mod 365 asked for file 3039, Nexus sent OLD_VERSION 1028.
        queue = BrowserQueue()
        queue.add("sb", 365, 3039, "u3039", staged={3038})
        step = queue.advance("sb", 365, {3038, 1028})
        self.assertEqual((step.action, step.unexpected), (STAY, (1028,)))
        self.assertEqual(queue.waiting_for("sb", 365), 3039)
        self.assertEqual(queue.advance("sb", 365, {3038, 1028}).unexpected, ())


if __name__ == "__main__":
    unittest.main()
