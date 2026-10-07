"""Decide when a Nexus window hides after a download starts, and when it returns."""

import unittest

from omamods.browser_hiding import HiddenWindows, files_in_state
from omamods.download_queue import (
    DOWNLOADING,
    FAILED,
    WAITING_FOR_BROWSER,
    DownloadStatus,
)


def status(file_id: int, state: str, mod_id: int = 1) -> DownloadStatus:
    return DownloadStatus("sb", mod_id, file_id, "f.zip", state, 0, None, 0, 0, 0, 0)


class HiddenWindowsTests(unittest.TestCase):
    def test_files_in_state_indexes_by_game_mod_file(self) -> None:
        statuses = (status(7, DOWNLOADING), status(8, FAILED))
        self.assertEqual(files_in_state(statuses, FAILED), {("sb", 1, 8)})

    def test_hides_once_when_the_shown_file_starts(self) -> None:
        hidden = HiddenWindows()
        waiting = {("sb", 1): 7}
        self.assertEqual(hidden.to_hide(waiting, (status(7, WAITING_FOR_BROWSER),)), ())
        self.assertEqual(
            hidden.to_hide(waiting, (status(7, DOWNLOADING),)), (("sb", 1),)
        )
        self.assertEqual(hidden.to_hide(waiting, (status(7, DOWNLOADING),)), ())

    def test_other_files_starting_do_not_hide_the_window(self) -> None:
        # File 8 is the next popup; only file 7's click has happened.
        hidden = HiddenWindows()
        self.assertEqual(hidden.to_hide({("sb", 1): 7}, (status(8, DOWNLOADING),)), ())
        self.assertEqual(
            hidden.to_hide({("sb", 1): 7}, (status(7, DOWNLOADING, 2),)), ()
        )

    def test_failure_restores_only_hidden_windows(self) -> None:
        hidden = HiddenWindows()
        waiting = {("sb", 1): 7, ("sb", 2): 9}
        failed = (status(7, FAILED), status(9, FAILED, 2))
        self.assertEqual(hidden.to_restore(waiting, failed), ())
        hidden.to_hide(waiting, (status(7, DOWNLOADING),))
        self.assertEqual(hidden.to_restore(waiting, failed), (("sb", 1),))
        self.assertEqual(hidden.hidden, set())

    def test_forget_allows_hiding_the_next_window(self) -> None:
        hidden = HiddenWindows()
        hidden.to_hide({("sb", 1): 7}, (status(7, DOWNLOADING),))
        hidden.forget(("sb", 1))
        self.assertEqual(
            hidden.to_hide({("sb", 1): 8}, (status(8, DOWNLOADING),)), (("sb", 1),)
        )


if __name__ == "__main__":
    unittest.main()
