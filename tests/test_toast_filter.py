"""Repeated install errors show one toast until it would time out."""

import unittest

from omamods.tui.toast_filter import RepeatedToastFilter


class FakeClock:
    """A monotonic clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class RepeatedToastFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.toasts = RepeatedToastFilter(10, self.clock)

    def test_same_error_shows_once_while_on_screen(self) -> None:
        # Regression: three i presses stacked three identical refusals.
        shown = [self.toasts.should_show("refused") for _ in range(3)]
        self.assertEqual(shown, [True, False, False])

    def test_same_error_shows_again_after_its_timeout(self) -> None:
        self.toasts.should_show("refused")
        self.clock.now += 10.5
        self.assertTrue(self.toasts.should_show("refused"))

    def test_different_errors_each_show(self) -> None:
        self.assertTrue(self.toasts.should_show("refused"))
        self.assertTrue(self.toasts.should_show("file changed"))
