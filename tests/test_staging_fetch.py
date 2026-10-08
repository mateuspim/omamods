"""Exercise staging layout, Nexus page fetching, and per-file install records."""

from pathlib import Path
import tempfile
import unittest

from omamods.install_records import (
    file_state_path,
    installed_file_ids,
    legacy_state_path,
)
from omamods.mod_fetch import (
    BrowserDownloadRequired,
    stage_file,
    stage_mod_details,
    stage_nxm_link,
)
from omamods.nexus_api import (
    NexusApi,
    NexusPage,
    parse_file_listing,
    parse_mod_info,
    parse_nxm_link,
)
from omamods.nexus_workflow import revert_mod_files
from omamods.pak_games import PAK_OVERLAY_GAMES, PakGameCatalog
from omamods.staging import (
    list_staged_mods,
    picture_path,
    remove_staged_archive,
    staged_archives,
)
from tests.fakes import FakeNexusSite

SB = PAK_OVERLAY_GAMES["stellar-blade"]
PAGE = NexusPage("stellarblade", 1)


class TemporaryRoot(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()


class NexusMetadataTests(unittest.TestCase):
    def test_mod_info_requires_https_picture(self) -> None:
        self.assertIsNone(parse_mod_info({"name": "A"}).picture_url)
        with self.assertRaisesRegex(ValueError, "picture_url"):
            parse_mod_info({"name": "A", "picture_url": "http://x/a.png"})

    def test_mod_info_reads_the_adult_flag(self) -> None:
        self.assertFalse(parse_mod_info({"name": "A"}).adult)
        flagged = parse_mod_info({"name": "A", "contains_adult_content": True})
        self.assertTrue(flagged.adult)

    def test_file_listing_keeps_display_details(self) -> None:
        listed = parse_file_listing(FakeNexusSite().get_json("files.json", "k"))
        self.assertEqual((listed[0].display_name, listed[0].size_kb), ("Black", 2048))

    def test_catalog_maps_domains(self) -> None:
        self.assertIs(PakGameCatalog().for_domain("stellarblade"), SB)
        with self.assertRaisesRegex(ValueError, "expected one of"):
            PakGameCatalog().for_domain("skyrim")


class StagingTests(TemporaryRoot):
    def test_details_picture_and_listing(self) -> None:
        site = FakeNexusSite()
        staged = stage_mod_details(NexusApi(site, "k"), SB, PAGE, self.root)
        self.assertEqual(staged.title, "Sample Outfit")
        self.assertEqual(staged.picture.read_bytes(), b"picture")
        self.assertEqual([f.file_id for f in staged.files], [7, 8])
        self.assertEqual(list_staged_mods(self.root, SB), (staged,))

    def test_picture_named_by_content_not_url(self) -> None:
        # Nexus' CDN served WebP bytes for '.png' and '.jpeg' picture URLs.
        site = FakeNexusSite()
        site.picture = b"RIFF\x00\x00\x00\x00WEBPVP8 "
        staged = stage_mod_details(NexusApi(site, "k"), SB, PAGE, self.root)
        self.assertEqual(staged.picture.name, "picture.webp")

    def test_picture_failure_does_not_block_staging(self) -> None:
        site = FakeNexusSite(picture_online=False)
        staged = stage_mod_details(NexusApi(site, "k"), SB, PAGE, self.root)
        self.assertIsNone(staged.picture)
        self.assertEqual(list(staged.archives), [])

    def test_partial_downloads_are_not_listed(self) -> None:
        folder = self.root / "7"
        folder.mkdir()
        (folder / ".tmpx.partial").write_bytes(b"")
        self.assertEqual(staged_archives(self.root), {})
        (folder / "Black.zip").write_bytes(b"z")
        self.assertEqual(staged_archives(self.root), {7: folder / "Black.zip"})

    def test_picture_suffix_defaults_to_jpg(self) -> None:
        self.assertEqual(picture_path(self.root, "https://x/a.PNG").name, "picture.png")
        self.assertEqual(picture_path(self.root, "https://x/a").name, "picture.jpg")

    def test_hand_downloaded_archive_listed_without_details(self) -> None:
        archive = self.root / "archives/stellar-blade/5/0/Manual.zip"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"z")
        (mod,) = list_staged_mods(self.root, SB)
        self.assertEqual((mod.title, mod.files[0].file_name), ("Mod 5", "Manual.zip"))


class RemoveStagedTests(TemporaryRoot):
    def test_removes_archive_and_empty_folder_but_not_installed(self) -> None:
        archive = self.root / "archives/stellar-blade/365/1028/Old.rar"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"r")
        removed = remove_staged_archive(self.root, SB, 365, 1028)
        self.assertEqual(removed, archive)
        self.assertFalse(archive.parent.exists())
        with self.assertRaisesRegex(ValueError, "expected a staged archive"):
            remove_staged_archive(self.root, SB, 365, 1028)

    def test_refuses_installed_file(self) -> None:
        archive = self.root / "archives/stellar-blade/1/7/Black.zip"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"z")
        record = file_state_path(self.root, SB, 1, 7, None)
        record.parent.mkdir(parents=True)
        record.write_text("{}")
        with self.assertRaisesRegex(ValueError, "uninstall it first"):
            remove_staged_archive(self.root, SB, 1, 7)
        self.assertTrue(archive.is_file())


class DownloadTests(TemporaryRoot):
    def test_premium_downloads_into_staging(self) -> None:
        api = NexusApi(FakeNexusSite(), "k")
        file = api.files(PAGE)[0]
        archive = stage_file(api, SB, PAGE, file, self.root, None)
        self.assertEqual(archive, self.root / "archives/stellar-blade/1/7/Black.zip")
        self.assertEqual(archive.read_bytes(), b"archive")

    def test_non_premium_needs_browser_click(self) -> None:
        api = NexusApi(FakeNexusSite(premium=False), "k")
        with self.assertRaises(BrowserDownloadRequired) as raised:
            stage_file(api, SB, PAGE, api.files(PAGE)[0], self.root, None)
        self.assertIn("stellarblade/mods/1?tab=files&file_id=7", raised.exception.url)

    def test_nxm_click_stages_details_and_file(self) -> None:
        api = NexusApi(FakeNexusSite(premium=False), "k")
        link = parse_nxm_link("nxm://stellarblade/mods/1/files/8?key=a&expires=9")
        clicked = stage_nxm_link(api, self.root, link, PakGameCatalog())
        game, archive = clicked.game, clicked.archive
        self.assertEqual(clicked.describe(), "Hair 1.0 (OPTIONAL)")
        self.assertIs(game, SB)
        self.assertEqual(archive.name, "Hair.zip")
        self.assertTrue((archive.parents[1] / "mod.json").is_file())


class InstallRecordTests(TemporaryRoot):
    def test_legacy_and_per_file_records(self) -> None:
        legacy = legacy_state_path(self.root, SB, 1)
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{"file_id": 0}')
        per_file = file_state_path(self.root, SB, 1, 7, None)
        per_file.parent.mkdir()
        per_file.write_text("{}")
        self.assertEqual(installed_file_ids(self.root, SB, 1), {0, 7})

    def test_revert_reports_missing_file_record(self) -> None:
        with self.assertRaisesRegex(ValueError, "file=7: expected install state"):
            revert_mod_files(SB, self.root, 1, 7)


if __name__ == "__main__":
    unittest.main()
