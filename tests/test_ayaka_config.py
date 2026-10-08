"""Save and read the AyakaMods login cookie in the private config."""

from pathlib import Path
import tomllib
import unittest

from omamods.ayaka_config import (
    load_login_cookie,
    normalize_cookie,
    read_login_cookie,
    save_login_cookie,
    with_login_cookie,
)
from tests.fakes import FakeConfigFiles

COOKIE = "347376%2CAbC_d-9"
CONFIG = Path("/config/omamods/config.toml")


class NormalizeCookieTest(unittest.TestCase):
    def test_accepts_the_value_or_the_header_form(self) -> None:
        for text in (COOKIE, f" xf_user={COOKIE} ", f'"{COOKIE}"', "347376,AbC_d-9"):
            with self.subTest(text=text):
                self.assertIn(normalize_cookie(text), (COOKIE, "347376,AbC_d-9"))

    def test_refuses_other_cookies_and_spaces(self) -> None:
        for text in ("", "xf_session=abc", "347376 AbC", "abc,def"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "xf_user"):
                normalize_cookie(text)


class WithLoginCookieTest(unittest.TestCase):
    def test_appends_a_table_after_mods(self) -> None:
        source = '[nexus]\napi_key = "k"\n\n[[mods]]\ngame = "cronos"\nurl = "u"\n'
        updated = with_login_cookie(source, COOKIE)
        fields = tomllib.loads(updated)
        self.assertEqual(fields["ayaka"]["login_cookie"], COOKIE)
        self.assertEqual(fields["mods"], [{"game": "cronos", "url": "u"}])

    def test_replaces_a_saved_cookie(self) -> None:
        source = '[ayaka]\nlogin_cookie = "1%2Cold"\n'
        self.assertEqual(read_login_cookie(with_login_cookie(source, COOKIE)), COOKIE)

    def test_fills_an_empty_table(self) -> None:
        self.assertEqual(
            read_login_cookie(with_login_cookie("[ayaka]\n", COOKIE)), COOKIE
        )


class LoadAndSaveTest(unittest.TestCase):
    def test_missing_config_reads_empty_then_saves_privately(self) -> None:
        files = FakeConfigFiles()
        self.assertEqual(load_login_cookie(CONFIG, files), "")
        save_login_cookie(CONFIG, Path("/data/omamods"), COOKIE, files)
        self.assertEqual(load_login_cookie(CONFIG, files), COOKIE)

    def test_a_wrong_type_is_named(self) -> None:
        with self.assertRaisesRegex(ValueError, "login_cookie=1"):
            read_login_cookie("[ayaka]\nlogin_cookie = 1\n")


if __name__ == "__main__":
    unittest.main()
