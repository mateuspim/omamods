"""Summarise and title download-queue entries for the queue views."""

import unittest

from omamods.download_queue import DownloadStatus
from omamods.tui.download_rows import (
    DownloadTitles,
    active_download,
    queue_summary,
    retry_outcome,
)

NOW = 1000.0


def entry(
    game: str, mod: int, state: str, received: int = 0, progressed: float = NOW
) -> DownloadStatus:
    return DownloadStatus(
        game,
        mod,
        mod * 10,
        f"{mod}.zip",
        state,
        received,
        1000,
        2048.0,
        0,
        0,
        progressed,
    )


def title(status: DownloadStatus) -> str:
    return f"Mod {status.mod_id}"


class FakeRetryService:
    """Answer retries like ModsService: True when staged, False for a click."""

    def __init__(self, staged: bool) -> None:
        self.staged = staged
        self.retried: list[DownloadStatus] = []

    def retry(self, status: DownloadStatus) -> bool:
        self.retried.append(status)
        return self.staged


class FakeTitleService:
    """Look titles up like ModsService, failing for unknown games."""

    def __init__(self) -> None:
        self.lookups = 0
        self.catalog = self

    def get(self, game_id: str) -> str:
        if game_id != "cyberpunk-2077":
            raise ValueError(f"game={game_id!r}: expected 'cyberpunk-2077'")
        return game_id

    def staged_mod(self, game: str, mod_id: int) -> "FakeTitleService":
        self.lookups += 1
        self.title = f"Cyber mod {mod_id}"
        return self


class SummaryTests(unittest.TestCase):
    def test_empty_queue(self) -> None:
        self.assertEqual(queue_summary((), "g", title, NOW), "↓ Downloads: queue empty")

    def test_counts_every_game_busiest_first(self) -> None:
        statuses = (
            entry("a", 1, "done"),
            entry("b", 2, "waiting for browser"),
            entry("a", 3, "done"),
            entry("b", 4, "failed"),
        )
        self.assertEqual(
            queue_summary(statuses, "a", title, NOW),
            "↓ Downloads: 1 waiting for browser · 1 failed · 2 done",
        )

    def test_names_only_this_games_running_download(self) -> None:
        statuses = (entry("other", 1, "downloading", 500), entry("a", 2, "done"))
        self.assertEqual(
            queue_summary(statuses, "a", title, NOW),
            "↓ Downloads: 1 downloading · 1 done",
        )
        statuses += (entry("a", 3, "downloading", 450),)
        self.assertEqual(
            queue_summary(statuses, "a", title, NOW),
            "↓ Downloads: 2 downloading (Mod 3 45% · 2.0 KB/s) · 1 done",
        )

    def test_stalled_downloads_are_not_active(self) -> None:
        stalled = entry("a", 1, "downloading", 10, progressed=NOW - 60)
        self.assertIsNone(active_download((stalled,), "a", NOW))
        self.assertEqual(
            queue_summary((stalled,), "a", title, NOW), "↓ Downloads: 1 stalled"
        )


class TitleTests(unittest.TestCase):
    def test_titles_are_cached_and_fall_back(self) -> None:
        service = FakeTitleService()
        titles = DownloadTitles(service)
        self.assertEqual(titles(entry("cyberpunk-2077", 7, "done")), "Cyber mod 7")
        self.assertEqual(titles(entry("cyberpunk-2077", 7, "done")), "Cyber mod 7")
        self.assertEqual(service.lookups, 1)
        self.assertEqual(titles(entry("gone", 8, "done")), "gone mod 8")


class RetryTests(unittest.TestCase):
    def test_retry_asks_for_a_click_only_when_needed(self) -> None:
        status = entry("a", 1, "failed")
        self.assertIsNone(retry_outcome(FakeRetryService(True), status))
        message = retry_outcome(FakeRetryService(False), status)
        self.assertEqual(message, "1.zip: click 'Mod Manager Download' on Nexus.")


if __name__ == "__main__":
    unittest.main()
