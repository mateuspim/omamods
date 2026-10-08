"""Stage AyakaMods details and browser downloads in Ayaka's own storage area."""

from pathlib import Path
import re
import tempfile
import unittest

from omamods.ayaka_pages import AyakaPage, parse_mod_page
from omamods.ayaka_staging import (
    ayaka_root,
    claim_ayaka_archive,
    require_game,
    stage_ayaka_details,
)
from omamods.ayaka_wait import AyakaWaits
from omamods.browser_windows import ayaka_window_class
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.staging import load_staged_mod
from tests.fakes import FakeAyakaPages, FakeNexusSite
from tests.test_ayaka_pages import MOD_BLOCK, page_html

SB = PAK_OVERLAY_GAMES["stellar-blade"]
PAGE_URL = "https://ayakamods.com/mods/7322/"


def stellar_page(**fields: str) -> str:
    image = "https://ayakamods.com/data/mod_icons/7/7322.png"
    return page_html({**MOD_BLOCK, "genre": "Stellar Blade", "image": image, **fields})


class RequireGameTest(unittest.TestCase):
    def test_matches_folded_titles(self) -> None:
        require_game(parse_mod_page(stellar_page(genre="Stellar Blade™")), SB)

    def test_refuses_another_game_and_names_both(self) -> None:
        details = parse_mod_page(stellar_page(genre="Helldivers 2"))
        with self.assertRaisesRegex(ValueError, "Helldivers 2.*Stellar Blade"):
            require_game(details, SB)


class TemporaryRoot(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)
        self.root = ayaka_root(self.storage)


class StageDetailsTest(TemporaryRoot):
    def test_saves_details_and_picture_under_ayaka(self) -> None:
        site = FakeNexusSite()
        pages = FakeAyakaPages({PAGE_URL: stellar_page()})
        mod = stage_ayaka_details(pages, site, SB, AyakaPage(7322), self.root)
        self.assertEqual(self.root, self.storage / "ayaka")
        self.assertEqual(mod.info.name if mod.info else None, "Sample Retexture")
        self.assertEqual(
            mod.picture, self.root / "archives/stellar-blade/7322/picture.png"
        )
        self.assertEqual(mod.files, ())

    def test_refuses_before_writing_anything(self) -> None:
        pages = FakeAyakaPages({PAGE_URL: stellar_page(genre="Helldivers 2")})
        with self.assertRaisesRegex(ValueError, "Helldivers 2"):
            stage_ayaka_details(pages, FakeNexusSite(), SB, AyakaPage(7322), self.root)
        self.assertFalse(self.root.exists())


class ClaimArchiveTest(TemporaryRoot):
    def _download(self, name: str) -> Path:
        downloads = self.storage / "Downloads"
        downloads.mkdir(exist_ok=True)
        archive = downloads / name
        archive.write_bytes(b"zip")
        return archive

    def test_numbers_each_arrival_and_records_it(self) -> None:
        pages = FakeAyakaPages({PAGE_URL: stellar_page()})
        stage_ayaka_details(pages, FakeNexusSite(), SB, AyakaPage(7322), self.root)
        first = claim_ayaka_archive(self.root, SB, 7322, self._download("A.zip"))
        second = claim_ayaka_archive(self.root, SB, 7322, self._download("B.zip"))
        self.assertEqual((first.file_id, second.file_id), (1, 2))
        mod = load_staged_mod(self.root, SB, 7322)
        self.assertEqual([f.file_name for f in mod.files], ["A.zip", "B.zip"])
        self.assertEqual({f.category for f in mod.files}, {"MAIN"})
        self.assertEqual(sorted(mod.archives), [1, 2])

    def test_without_details_the_file_still_stages(self) -> None:
        file = claim_ayaka_archive(self.root, SB, 9, self._download("A.zip"))
        mod = load_staged_mod(self.root, SB, 9)
        self.assertEqual((file.file_id, list(mod.archives)), (1, [1]))


class AyakaWaitsTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.downloads = Path(temporary.name)

    def test_reports_a_finished_file_once_then_stops(self) -> None:
        waits = AyakaWaits(self.downloads)
        self.assertIsNone(waits.start("sb", 1))
        (self.downloads / "a.zip").write_bytes(b"zip")
        self.assertIsNone(waits.arrivals())
        result = waits.arrivals()
        assert result is not None
        self.assertEqual(
            (result[0].mod_id, result[1]), (1, (self.downloads / "a.zip",))
        )
        self.assertIsNone(waits.current)

    def test_a_new_wait_replaces_the_old_one(self) -> None:
        waits = AyakaWaits(self.downloads)
        waits.start("sb", 1)
        replaced = waits.start("sb", 2)
        self.assertEqual(replaced.mod_id if replaced else None, 1)
        stopped = waits.cancel()
        self.assertEqual(
            (stopped.mod_id if stopped else None, waits.cancel()), (2, None)
        )


class AyakaWindowClassTest(unittest.TestCase):
    def test_matches_only_that_mod(self) -> None:
        pattern = ayaka_window_class(42)
        self.assertTrue(pattern.search("brave-ayakamods.com__mods_42_-Default"))
        self.assertTrue(pattern.search("brave-ayakamods.com__mods_42-Default"))
        self.assertFalse(pattern.search("brave-ayakamods.com__mods_421-Default"))
        self.assertIsInstance(pattern, re.Pattern)


if __name__ == "__main__":
    unittest.main()
