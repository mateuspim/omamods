"""Exercise the shared download queue: progress, speed, stalls, and retries."""

from dataclasses import replace
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from omamods.download_queue import (
    DONE,
    DOWNLOADING,
    FAILED,
    STALLED,
    WAITING_FOR_BROWSER,
    DownloadLog,
    DownloadStatus,
    ProgressRecorder,
    shown_state,
)
from omamods.mod_fetch import BrowserDownloadRequired, download_log, stage_file
from omamods.cdn_download import (
    RetryPolicy,
    copy_with_progress,
    download_request,
    encoded_download_url,
)
from omamods.nexus_api import (
    NexusApi,
    NexusFile,
    NexusPage,
)
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.tui.download_rows import eta_text, human_bytes, progress_text
from tests.fakes import FakeNexusSite, FakeSleep

FILE = NexusFile(7, "Black.zip", "MAIN", 0, size_kb=4)
SB = PAK_OVERLAY_GAMES["stellar-blade"]
FAST = RetryPolicy(sleep=FakeSleep())


class FakeClock:
    """Advance time only when a test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class QueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.clock = FakeClock()
        self.log = DownloadLog(Path(self.temporary.name), self.clock)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_progress_speed_and_completion(self) -> None:
        status = self.log.begin("stellar-blade", 1, FILE, DOWNLOADING)
        self.assertEqual(status.total, 4096)
        recorder = ProgressRecorder(self.log, status)
        self.clock.now += 2
        recorder(2048, 4096)
        (written,) = self.log.statuses()
        self.assertEqual((written.received, written.bytes_per_second), (2048, 1024.0))
        self.log.finish(recorder.status, None)
        self.assertEqual(self.log.statuses()[0].state, DONE)

    def test_retry_note_shows_then_clears_when_bytes_flow(self) -> None:
        recorder = ProgressRecorder(
            self.log, self.log.begin("sb", 1, FILE, DOWNLOADING)
        )
        recorder.note_retry(1, OSError("Connection reset by peer"))
        noted = self.log.statuses()[0]
        self.assertEqual(noted.error, "retrying 2/5 after: Connection reset by peer")
        self.assertEqual(shown_state(noted, noted.progressed + 5), DOWNLOADING)
        self.clock.now += 1
        recorder(10, None)
        self.assertEqual(recorder.status.error, "")

    def test_writes_are_throttled(self) -> None:
        recorder = ProgressRecorder(
            self.log, self.log.begin("sb", 1, FILE, DOWNLOADING)
        )
        recorder(1, None)
        self.clock.now += 0.1
        recorder(2, None)
        self.assertEqual(self.log.statuses()[0].received, 1)

    def test_no_new_bytes_shows_stalled(self) -> None:
        status = self.log.begin("sb", 1, FILE, DOWNLOADING)
        self.assertEqual(shown_state(status, status.progressed + 5), DOWNLOADING)
        self.assertEqual(shown_state(status, status.progressed + 60), STALLED)
        waiting = replace(status, state=WAITING_FOR_BROWSER)
        self.assertEqual(
            shown_state(waiting, status.progressed + 60), WAITING_FOR_BROWSER
        )

    def test_old_attempt_cannot_overwrite_retry(self) -> None:
        stale = self.log.begin("sb", 1, FILE, DOWNLOADING)
        self.log.begin("sb", 1, FILE, DOWNLOADING)
        self.log.finish(stale, "timed out")
        self.assertEqual(self.log.statuses()[0].state, DOWNLOADING)

    def test_clear_finished_keeps_active(self) -> None:
        self.log.finish(self.log.begin("sb", 1, FILE, DOWNLOADING), "boom")
        self.log.begin("sb", 2, FILE, DOWNLOADING)
        self.assertEqual(self.log.clear_finished(), 1)
        self.assertEqual([s.mod_id for s in self.log.statuses()], [2])

    def test_remove_forgets_one_entry(self) -> None:
        first = self.log.begin("sb", 1, FILE, WAITING_FOR_BROWSER)
        self.log.begin("sb", 2, FILE, WAITING_FOR_BROWSER)
        self.log.remove(first)
        self.assertEqual([s.mod_id for s in self.log.statuses()], [2])

    def test_clear_idle_keeps_only_moving_downloads(self) -> None:
        self.log.begin("sb", 1, FILE, WAITING_FOR_BROWSER)
        self.log.finish(self.log.begin("sb", 2, FILE, DOWNLOADING), None)
        self.log.begin("sb", 3, FILE, DOWNLOADING)
        self.assertEqual(self.log.clear_idle(), 2)
        self.assertEqual([s.mod_id for s in self.log.statuses()], [3])

    def test_unreadable_entries_are_skipped(self) -> None:
        (Path(self.temporary.name) / "broken.json").write_text("{")
        self.assertEqual(self.log.statuses(), ())


class StageFileQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.page = NexusPage("stellarblade", 1)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _stage(self, site: FakeNexusSite) -> None:
        stage_file(NexusApi(site, "k"), SB, self.page, FILE, self.root, None, FAST)

    def test_success_failure_and_browser_states(self) -> None:
        self._stage(FakeNexusSite())
        self.assertEqual(download_log(self.root).statuses()[0].state, DONE)
        failing = FakeNexusSite()
        failing.fail_downloads = True
        broken = replace(FILE, file_id=8, file_name="Hair.zip")
        with self.assertRaises(ValueError):
            stage_file(
                NexusApi(failing, "k"), SB, self.page, broken, self.root, None, FAST
            )
        with self.assertRaises(BrowserDownloadRequired):
            other = replace(FILE, file_id=9, file_name="Other.zip")
            stage_file(
                NexusApi(FakeNexusSite(premium=False), "k"),
                SB,
                self.page,
                other,
                self.root,
                None,
            )
        states = {
            s.file_id: (s.state, s.error) for s in download_log(self.root).statuses()
        }
        self.assertEqual(states[7], (DONE, ""))
        self.assertEqual(
            states[8], (FAILED, "Nexus HTTP 503: expected a downloadable file")
        )
        self.assertEqual(states[9][0], WAITING_FOR_BROWSER)


class DownloadUrlTests(unittest.TestCase):
    def test_raw_spaces_from_cdn_are_escaped_once(self) -> None:
        # Regression: Stellar Blade mod 409's CDN link had unescaped spaces.
        raw = (
            "https://cf-files.nexusmods.com/7804/100/Sample Outfit-100-1-1.rar"
            "?expires=1700000000&md5=SIGNATURE&user_id=1234"
        )
        encoded = encoded_download_url(raw)
        self.assertIn("/Sample%20Outfit-100-1-1.rar?expires=", encoded)
        self.assertTrue(encoded.endswith("&md5=SIGNATURE&user_id=1234"))
        self.assertEqual(encoded_download_url(encoded), encoded)

    def test_requests_identify_as_omamods(self) -> None:
        # Regression: the image CDN returned 403 to urllib's "Python-urllib" agent.
        built = download_request("https://staticdelivery.nexusmods.com/a b.png")
        self.assertEqual(built.get_header("User-agent"), "OmaMods/0.1.0")
        self.assertTrue(built.full_url.endswith("/a%20b.png"))


class FormattingTests(unittest.TestCase):
    def test_copy_reports_running_total(self) -> None:
        seen: list[int] = []
        copy_with_progress(
            BytesIO(b"x" * 600_000), BytesIO(), None, lambda r, t: seen.append(r)
        )
        self.assertEqual(seen[-1], 600_000)
        self.assertGreater(len(seen), 1)

    def test_human_sizes_progress_and_eta(self) -> None:
        self.assertEqual(human_bytes(1536), "1.5 KB")
        row = DownloadStatus(
            "sb", 1, 7, "a.zip", DOWNLOADING, 1024, 4096, 512.0, 0.0, 0.0, 0.0
        )
        self.assertEqual(progress_text(row), "25%  1.0 KB / 4.0 KB")
        self.assertEqual(eta_text(row), "0m 06s")
        self.assertEqual(eta_text(replace(row, state=DONE)), "")


if __name__ == "__main__":
    unittest.main()
