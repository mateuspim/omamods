"""Exercise resumable CDN downloads and retries of dropped connections."""

from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from omamods.cdn_download import (
    NexusHttpError,
    RetryPolicy,
    TransientDownloadError,
    copy_response,
    download_with_retries,
    is_transient,
)
from omamods.download_queue import DONE, FAILED
from omamods.mod_fetch import download_log, stage_file
from omamods.nexus_api import NexusApi, NexusFile, NexusPage
from omamods.pak_games import PAK_OVERLAY_GAMES
from tests.fakes import FakeNexusSite, FakeSleep

SB = PAK_OVERLAY_GAMES["stellar-blade"]
PAGE = NexusPage("stellarblade", 533)
FILE = NexusFile(5227, "Sample Outfit.zip", "OPTIONAL", 0)
BODY = b"0123456789abcdef"


def resetting_site(resets: int) -> FakeNexusSite:
    site = FakeNexusSite()
    site.archive = BODY
    site.connection_resets = resets
    return site


class RetryRulesTests(unittest.TestCase):
    def test_only_temporary_failures_are_retried(self) -> None:
        self.assertTrue(is_transient(TransientDownloadError("reset")))
        self.assertTrue(is_transient(NexusHttpError(503, "x")))
        self.assertTrue(is_transient(NexusHttpError(429, "x")))
        for permanent in (403, 404, 410):
            self.assertFalse(is_transient(NexusHttpError(permanent, "x")))
        self.assertFalse(is_transient(ValueError("bad URL")))

    def test_backoff_doubles(self) -> None:
        policy = RetryPolicy()
        self.assertEqual([policy.delay(n) for n in (1, 2, 3, 4)], [2.0, 4.0, 8.0, 16.0])


class ResumeTests(unittest.TestCase):
    def test_dropped_connections_resume_where_they_stopped(self) -> None:
        site, sleep, notes = resetting_site(2), FakeSleep(), []
        policy = RetryPolicy(sleep=sleep, on_retry=lambda n, e: notes.append(n))
        stream = BytesIO()
        download_with_retries(site, "https://cdn/x.zip", stream, None, policy)
        self.assertEqual(stream.getvalue(), BODY)
        self.assertEqual(site.resume_offsets, [0, 3, 6])
        self.assertEqual((sleep.delays, notes), ([2.0, 4.0], [1, 2]))

    def test_gives_up_after_the_last_attempt(self) -> None:
        site, sleep = resetting_site(10), FakeSleep()
        with self.assertRaisesRegex(TransientDownloadError, "Connection reset"):
            download_with_retries(
                site, "https://cdn/x.zip", BytesIO(), None, RetryPolicy(sleep=sleep)
            )
        self.assertEqual(len(site.resume_offsets), 5)

    def test_permanent_refusal_is_not_retried(self) -> None:
        site = FakeNexusSite(picture_online=False)
        with self.assertRaises(NexusHttpError):
            download_with_retries(
                site,
                "https://cdn/a.png",
                BytesIO(),
                None,
                RetryPolicy(sleep=FakeSleep()),
            )
        self.assertEqual(len(site.downloads), 1)

    def test_ignored_range_restarts_from_zero(self) -> None:
        stream = BytesIO(b"012")
        stream.seek(3)
        copy_response(BytesIO(BODY), 200, str(len(BODY)), stream, None, 3)
        self.assertEqual(stream.getvalue(), BODY)

    def test_partial_content_appends_with_full_total(self) -> None:
        stream, seen = BytesIO(b"012"), []
        stream.seek(3)
        copy_response(
            BytesIO(BODY[3:]), 206, "13", stream, lambda r, t: seen.append((r, t)), 3
        )
        self.assertEqual((stream.getvalue(), seen[-1]), (BODY, (16, 16)))


class StagedRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _stage(self, site: FakeNexusSite) -> Path:
        api = NexusApi(site, "k")
        return stage_file(
            api, SB, PAGE, FILE, self.root, None, RetryPolicy(sleep=FakeSleep())
        )

    def test_mod_533_reset_now_recovers(self) -> None:
        # Regression: one 'Connection reset by peer' used to fail the download.
        archive = self._stage(resetting_site(1))
        self.assertEqual(archive.read_bytes(), BODY)
        (status,) = download_log(self.root).statuses()
        self.assertEqual((status.state, status.error), (DONE, ""))

    def test_persistent_failure_is_recorded_and_leaves_no_folder(self) -> None:
        with self.assertRaises(TransientDownloadError):
            self._stage(resetting_site(10))
        (status,) = download_log(self.root).statuses()
        self.assertEqual(status.state, FAILED)
        self.assertFalse((self.root / "archives/stellar-blade/533/5227").exists())


if __name__ == "__main__":
    unittest.main()
