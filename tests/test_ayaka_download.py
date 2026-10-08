"""Find and fetch AyakaMods files as the logged-in user, without the network."""

from pathlib import Path
import tempfile
import unittest
from urllib import request

from omamods.ayaka_download import (
    AyakaHostedElsewhere,
    AyakaLoginRequired,
    SameSiteCookieRedirects,
    attachment_name,
    download_url,
    list_offers,
    parse_file_choices,
)
from omamods.ayaka_fetch import stage_ayaka_offer
from omamods.ayaka_pages import AyakaPage
from omamods.download_queue import DONE, DownloadLog, DownloadStatus
from omamods.mod_sites import AYAKA_SITE
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.staging import load_staged_mod, save_mod_details
from omamods.nexus_api import NexusModInfo
from tests.fakes import FakeAyakaSession

SB = PAK_OVERLAY_GAMES["stellar-blade"]
PAGE = AyakaPage(7311)
URL = "https://ayakamods.com/mods/7311/download"
CHOOSER = """<html data-logged-in="true"><body>
<a href="/mods/sample-suit.7311/download?file=60788" class="button">Suit-Black.zip <span>12 MB</span></a>
<a href="/mods/sample-suit.7311/download?file=60789&amp;v=2">Suit-Red.zip</a>
<a href="/mods/sample-suit.7311/download?file=60788">Suit-Black.zip</a>
<a href="/mods/other.999/download?file=1">Other mod</a>
<a href="https://evil.example/mods/7311/download?file=5">Elsewhere</a>
</body></html>"""


class AttachmentNameTest(unittest.TestCase):
    def test_reads_plain_and_encoded_names(self) -> None:
        self.assertEqual(attachment_name('attachment; filename="a b.zip"'), "a b.zip")
        self.assertEqual(
            attachment_name("attachment; filename*=UTF-8''%E6%88%98.zip"), "战.zip"
        )

    def test_refuses_missing_and_path_names(self) -> None:
        for header in (None, "attachment", 'attachment; filename="../x.zip"'):
            with self.subTest(header=header):
                self.assertIsNone(attachment_name(header))


class FileChoicesTest(unittest.TestCase):
    def test_lists_this_mods_files_once_each(self) -> None:
        offers = parse_file_choices(CHOOSER, 7311)
        self.assertEqual([o.attachment_id for o in offers], [60788, 60789])
        self.assertEqual(offers[0].label, "Suit-Black.zip 12 MB")
        self.assertEqual(
            offers[1].url,
            "https://ayakamods.com/mods/sample-suit.7311/download?file=60789&v=2",
        )


class ListOffersTest(unittest.TestCase):
    def test_a_direct_file_is_the_only_offer(self) -> None:
        session = FakeAyakaSession()
        session.serve_file(URL, "Suit.zip", b"zip")
        offers = list_offers(session, PAGE)
        self.assertEqual(
            [(o.url, o.label, o.attachment_id) for o in offers],
            [(URL, "Suit.zip", None)],
        )
        self.assertEqual(download_url(PAGE), URL)

    def test_a_chooser_page_lists_its_files(self) -> None:
        session = FakeAyakaSession()
        session.serve_page(URL, CHOOSER)
        self.assertEqual(len(list_offers(session, PAGE)), 2)

    def test_a_logged_out_page_asks_for_the_cookie(self) -> None:
        session = FakeAyakaSession()
        session.serve_page(URL, '<html data-logged-in="false">You must log in</html>')
        with self.assertRaisesRegex(AyakaLoginRequired, "xf_user"):
            list_offers(session, PAGE)

    def test_a_redirect_off_site_is_hosted_elsewhere(self) -> None:
        session = FakeAyakaSession()
        session.serve_page(URL, "<html></html>", "https://mega.nz/file/abc")
        with self.assertRaisesRegex(AyakaHostedElsewhere, "mega.nz"):
            list_offers(session, PAGE)

    def test_a_page_without_links_names_the_page(self) -> None:
        session = FakeAyakaSession()
        session.serve_page(URL, '<html data-logged-in="true">Nothing</html>')
        with self.assertRaisesRegex(ValueError, "expected a file or links"):
            list_offers(session, PAGE)


class CookieRedirectTest(unittest.TestCase):
    def _redirect(self, new_url: str) -> request.Request:
        original = request.Request(URL, headers={"Cookie": "xf_user=1%2Cab"})
        handler = SameSiteCookieRedirects()
        new = handler.redirect_request(original, None, 302, "Found", {}, new_url)  # type: ignore[arg-type]
        assert new is not None
        return new

    def test_keeps_the_cookie_on_ayakamods(self) -> None:
        new = self._redirect("https://ayakamods.com/data/file.zip")
        self.assertEqual(new.get_header("Cookie"), "xf_user=1%2Cab")

    def test_drops_the_cookie_on_other_hosts(self) -> None:
        self.assertIsNone(
            self._redirect("https://cdn.example/file.zip").get_header("Cookie")
        )


class StageOfferTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.log = DownloadLog(self.root / "downloads")
        info = NexusModInfo("Suit", "", "", "1.0", None)
        save_mod_details(self.root / "archives/stellar-blade/7311", info, ())

    def test_downloads_into_staging_and_the_queue(self) -> None:
        session = FakeAyakaSession()
        session.serve_page(URL, CHOOSER)
        file_url = parse_file_choices(CHOOSER, 7311)[1].url
        session.serve_file(file_url, "Suit-Red.zip", b"red zip")
        offer = list_offers(session, PAGE)[1]
        path = stage_ayaka_offer(session, self.root, SB, 7311, offer, self.log)
        self.assertEqual(
            path, self.root / "archives/stellar-blade/7311/60789/Suit-Red.zip"
        )
        self.assertEqual(path.read_bytes(), b"red zip")
        mod = load_staged_mod(self.root, SB, 7311)
        self.assertEqual(
            [(f.file_id, f.file_name) for f in mod.files], [(60789, "Suit-Red.zip")]
        )
        (status,) = self.log.statuses()
        self.assertEqual(
            (status.site, status.state, status.file_id), (AYAKA_SITE, DONE, 60789)
        )

    def test_the_only_file_keeps_its_id_when_fetched_again(self) -> None:
        session = FakeAyakaSession()
        session.serve_file(URL, "Suit.zip", b"zip")
        offer = list_offers(session, PAGE)[0]
        first = stage_ayaka_offer(session, self.root, SB, 7311, offer, self.log)
        again = stage_ayaka_offer(session, self.root, SB, 7311, offer, self.log)
        self.assertEqual((first, first.parent.name), (again, "1"))
        self.assertEqual(session.downloads, [URL])  # The staged copy is reused.

    def test_a_web_page_instead_of_the_file_asks_for_the_cookie(self) -> None:
        session = FakeAyakaSession()
        session.serve_page(URL, '<html data-logged-in="true"></html>')
        offer = parse_file_choices(CHOOSER, 7311)[0]
        session.serve_page(offer.url, '<html data-logged-in="false"></html>')
        with self.assertRaisesRegex(AyakaLoginRequired, "expired"):
            stage_ayaka_offer(session, self.root, SB, 7311, offer, self.log)


class QueueKeyTest(unittest.TestCase):
    def test_ayaka_entries_never_share_a_nexus_key(self) -> None:
        fields = ("sb", 1, 7, "a.zip", DONE, 0, None, 0.0, 0.0, 0.0, 0.0)
        nexus = DownloadStatus(*fields)
        ayaka = DownloadStatus(*fields, site=AYAKA_SITE)
        self.assertEqual((nexus.key, ayaka.key), ("sb-1-7", "ayaka-sb-1-7"))


if __name__ == "__main__":
    unittest.main()
