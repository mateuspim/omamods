"""Read Codeberg/GitHub releases and stage them beside Nexus' staging."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from omamods.cdn_download import RetryPolicy
from omamods.download_queue import DownloadLog
from omamods.mod_sites import RELEASE_SITE
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.release_api import fetch_latest_release, parse_latest_release
from omamods.release_sources import (
    ReleaseSource,
    release_source,
    sources_for,
)
from omamods.release_staging import (
    load_release_mod,
    pending_update,
    release_root,
    stage_release_asset,
    stage_release_details,
)
from tests.fakes import FakeReleaseTransport, FakeSleep, codeberg_release

MGSV = PAK_OVERLAY_GAMES["metalgearsolidvtpp"]
MGSVFIX = release_source("metalgearsolidvtpp", 1)


class SourceTests(unittest.TestCase):
    def test_mgsvfix_points_at_codeberg(self) -> None:
        self.assertEqual(MGSVFIX.page_url, "https://codeberg.org/Lyall/MGSVFix")
        self.assertEqual(
            MGSVFIX.latest_release_url,
            "https://codeberg.org/api/v1/repos/Lyall/MGSVFix/releases/latest",
        )
        self.assertEqual(sources_for("metalgearsolidvtpp"), (MGSVFIX,))
        self.assertEqual(sources_for("cronos"), ())

    def test_github_uses_its_own_api(self) -> None:
        source = replace(MGSVFIX, forge="github")
        self.assertTrue(source.latest_release_url.startswith("https://api.github.com/"))

    def test_unknown_sources_and_forges_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "metalgearsolidvtpp/9"):
            release_source("metalgearsolidvtpp", 9)
        with self.assertRaisesRegex(ValueError, "gitlab"):
            ReleaseSource(1, "g", "gitlab", "o", "r", "s").page_url


class ParseTests(unittest.TestCase):
    def test_only_archives_become_files(self) -> None:
        release = parse_latest_release(codeberg_release(), MGSVFIX)
        self.assertEqual(release.tag, "0.0.3")
        (asset,) = release.assets
        self.assertEqual(asset.file.file_id, 9001)
        self.assertEqual(asset.file.file_name, "MGSVFix_0.0.3.zip")
        self.assertEqual((asset.file.category, asset.file.version), ("MAIN", "0.0.3"))
        self.assertEqual(asset.file.size_kb, 768)
        self.assertTrue(asset.url.startswith("https://codeberg.org/"))

    def test_fetch_asks_the_latest_release_url(self) -> None:
        transport = FakeReleaseTransport(codeberg_release())
        fetch_latest_release(transport, MGSVFIX)
        self.assertEqual(transport.requests, [MGSVFIX.latest_release_url])

    def test_bad_replies_name_the_field(self) -> None:
        reply = codeberg_release()
        cases = (
            ({**reply, "tag_name": 3}, "tag_name"),
            ({**reply, "published_at": "soon"}, "published_at"),
            ({**reply, "assets": []}, "expected a .zip"),
            ([], "expected an object"),
        )
        for value, message in cases:
            with self.assertRaisesRegex(ValueError, message):
                parse_latest_release(value, MGSVFIX)

    def test_plain_http_assets_are_refused(self) -> None:
        reply = codeberg_release()
        asset = dict(reply["assets"][0], browser_download_url="http://x/a.zip")
        with self.assertRaisesRegex(ValueError, "https"):
            parse_latest_release({**reply, "assets": [asset]}, MGSVFIX)


class StagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.storage = Path(self.temporary.name)
        self.root = release_root(self.storage)

    def _stage(self, tag: str, asset_id: int) -> None:
        reply = codeberg_release(tag, asset_id, f"MGSVFix_{tag}.zip")
        release = parse_latest_release(reply, MGSVFIX)
        stage_release_details(self.root, MGSV, MGSVFIX, release)

    def test_unfetched_source_is_listed_with_a_hint(self) -> None:
        mod = load_release_mod(self.root, MGSV, MGSVFIX)
        self.assertEqual(
            (mod.site, mod.title, mod.files), (RELEASE_SITE, "MGSVFix", ())
        )
        self.assertIn("Press d", mod.info.summary)

    def test_a_newer_release_demotes_the_old_file(self) -> None:
        self._stage("0.0.3", 9001)
        self._stage("0.0.4", 9100)
        mod = load_release_mod(self.root, MGSV, MGSVFIX)
        self.assertEqual(
            [(f.file_id, f.category) for f in mod.files],
            [(9100, "MAIN"), (9001, "OLD_VERSION")],
        )
        self.assertEqual(mod.info.version, "0.0.4")

    def test_download_lands_in_release_staging_and_the_queue(self) -> None:
        release = parse_latest_release(codeberg_release(), MGSVFIX)
        transport = FakeReleaseTransport(codeberg_release())
        log = DownloadLog(self.storage / "downloads")
        retry = RetryPolicy(sleep=FakeSleep())
        path = stage_release_asset(
            transport, self.root, MGSV, MGSVFIX, release.assets[0], log, retry
        )
        self.assertEqual(path.read_bytes(), b"release zip")
        self.assertTrue(
            path.is_relative_to(self.root / "archives/metalgearsolidvtpp/1")
        )
        self.assertEqual([s.site for s in log.statuses()], [RELEASE_SITE])

    def test_pending_update_needs_an_installed_older_file(self) -> None:
        self._stage("0.0.3", 9001)
        self._stage("0.0.4", 9100)
        mod = load_release_mod(self.root, MGSV, MGSVFIX)
        self.assertIsNone(pending_update(mod))
        installed = replace(mod, installed=frozenset({9001}))
        self.assertEqual(pending_update(installed).version, "0.0.4")
        current = replace(mod, installed=frozenset({9100}))
        self.assertIsNone(pending_update(current))


if __name__ == "__main__":
    unittest.main()
