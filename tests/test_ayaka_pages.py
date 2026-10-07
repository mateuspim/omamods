"""Read AyakaMods mod pages without contacting the site."""

import json
import unittest

from omamods.ayaka_pages import (
    AyakaPage,
    fetch_mod_details,
    is_ayaka_url,
    mod_page_url,
    parse_ayaka_page,
    parse_mod_page,
)
from tests.fakes import FakeAyakaPages

# Shaped like a live AyakaMods mod page (2026-10-07).
MOD_BLOCK = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Sample Retexture",
    "description": "A sample retexture for...",
    "image": "https://ayakamods.com/data/mod_icons/7/7322.webp?1700000000",
    "author": {"@type": "Person", "name": "Sample Author"},
    "dateModified": "2026-10-07T20:58:33+01:00",
    "softwareVersion": "1.2",
    "applicationSubCategory": "Game Modification",
    "genre": "Neverness to Everness",
}


def page_html(*blocks: object) -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(block)}</script>'
        for block in blocks
    )
    return f"<html><head>{scripts}</head><body></body></html>"


class ParseAyakaPageTest(unittest.TestCase):
    def test_reads_slugged_id_and_subpage_urls(self) -> None:
        urls = (
            "https://ayakamods.com/mods/sample-retexture.7322/",
            "https://www.ayakamods.com/mods/7322",
            "https://ayakamods.com/mods/sample-retexture.7322/updates",
            "https://ayakamods.com/mods/sample-%E6%A8%A1.7322/",
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(parse_ayaka_page(url), AyakaPage(7322))

    def test_rejects_other_sites_and_paths(self) -> None:
        urls = (
            "http://ayakamods.com/mods/a.1/",
            "https://evil.example/mods/a.1/",
            "https://ayakamods.com/games/neverness-to-everness.417/",
            "https://ayakamods.com/mods/latest-reviews",
        )
        for url in urls:
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "expected"):
                parse_ayaka_page(url)

    def test_tells_ayaka_links_apart(self) -> None:
        self.assertTrue(is_ayaka_url("https://ayakamods.com/mods/a.1/"))
        self.assertFalse(is_ayaka_url("https://www.nexusmods.com/sb/mods/1"))

    def test_links_the_id_only_page(self) -> None:
        self.assertEqual(
            mod_page_url(AyakaPage(7322)), "https://ayakamods.com/mods/7322/"
        )


class ParseModPageTest(unittest.TestCase):
    def test_reads_details_from_the_mod_block(self) -> None:
        details = parse_mod_page(page_html({"@type": "WebSite"}, MOD_BLOCK))
        self.assertEqual(details.info.name, "Sample Retexture")

    def test_reads_the_array_mod_pages_ship(self) -> None:
        # Regression: the live page wraps its blocks in one JSON array.
        blocks = [MOD_BLOCK, {"@type": "BreadcrumbList"}, {"@type": "WebPage"}]
        details = parse_mod_page(page_html(blocks))
        self.assertEqual(details.info.name, "Sample Retexture")
        self.assertEqual(details.info.author, "Sample Author")
        self.assertEqual(details.info.version, "1.2")
        self.assertEqual(details.info.picture_url, MOD_BLOCK["image"])
        self.assertEqual(details.game_name, "Neverness to Everness")
        self.assertEqual(details.modified, "2026-10-07T20:58:33+01:00")

    def test_skips_broken_blocks(self) -> None:
        html = '<script type="application/ld+json">{broken</script>'
        details = parse_mod_page(html + page_html(MOD_BLOCK))
        self.assertEqual(details.info.name, "Sample Retexture")

    def test_makes_relative_pictures_absolute(self) -> None:
        block = {**MOD_BLOCK, "image": "/data/attachments/36/a.jpg"}
        details = parse_mod_page(page_html(block))
        self.assertEqual(
            details.info.picture_url, "https://ayakamods.com/data/attachments/36/a.jpg"
        )

    def test_leaves_missing_fields_empty(self) -> None:
        block = {"name": "Bare", "applicationSubCategory": "Game Modification"}
        details = parse_mod_page(page_html(block))
        self.assertEqual((details.info.author, details.info.picture_url), ("", None))

    def test_refuses_pages_without_a_mod_block(self) -> None:
        with self.assertRaisesRegex(ValueError, "Game Modification"):
            parse_mod_page(page_html({"@type": "WebSite"}))

    def test_refuses_a_nameless_mod(self) -> None:
        block = {**MOD_BLOCK, "name": ""}
        with self.assertRaisesRegex(ValueError, "expected text"):
            parse_mod_page(page_html(block))

    def test_refuses_plain_http_pictures(self) -> None:
        block = {**MOD_BLOCK, "image": "http://cdn.example/a.jpg"}
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            parse_mod_page(page_html(block))


class FetchModDetailsTest(unittest.TestCase):
    def test_fetches_the_id_only_page(self) -> None:
        url = "https://ayakamods.com/mods/7322/"
        pages = FakeAyakaPages({url: page_html(MOD_BLOCK)})
        details = fetch_mod_details(pages, AyakaPage(7322))
        self.assertEqual(details.info.name, "Sample Retexture")
        self.assertEqual(pages.requests, [url])


if __name__ == "__main__":
    unittest.main()
