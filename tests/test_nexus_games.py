"""Match installed game titles to Nexus domains through a cached game list."""

import json
import os
from pathlib import Path
import tempfile
import unittest

from omamods.nexus_api import NexusApi
from omamods.nexus_games import (
    CACHE_MAX_AGE_SECONDS,
    NexusGameDirectory,
    load_game_directory,
    parse_game_directory,
    title_key,
    title_keys,
)
from tests.fakes import FakeNexusGamesTransport

GAMES = [
    {"name": "Stellar Blade", "domain_name": "stellarblade"},
    {"name": "Silent Hill 2 (2024)", "domain_name": "silenthill2"},
    {"name": "Kingdom Hearts III", "domain_name": "kingdomhearts3"},
    {"name": "Metal Gear Solid Delta: Snake Eater", "domain_name": "mgsdelta"},
]


class TitleKeyTests(unittest.TestCase):
    def test_folds_case_punctuation_and_trademarks(self) -> None:
        self.assertEqual(title_key("STAR WARS Jedi: Survivor™"), "starwarsjedisurvivor")

    def test_spells_out_greek_delta(self) -> None:
        self.assertEqual(title_key("MGS Δ"), "mgsdelta")

    def test_keys_drop_years_and_bundled_dlc(self) -> None:
        self.assertEqual(
            title_keys("Silent Hill 2 (2024)"), ("silenthill22024", "silenthill2")
        )
        self.assertEqual(title_keys("KH III + Re Mind (DLC)")[-1], "khiii")


class DirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = parse_game_directory(GAMES)

    def test_matches_steam_titles(self) -> None:
        self.assertEqual(self.directory.domain_for("SILENT HILL 2"), "silenthill2")
        self.assertEqual(
            self.directory.domain_for("KINGDOM HEARTS III + Re Mind (DLC)"),
            "kingdomhearts3",
        )
        self.assertEqual(
            self.directory.domain_for("METAL GEAR SOLID Δ: SNAKE EATER"), "mgsdelta"
        )

    def test_tries_each_title_in_order(self) -> None:
        self.assertEqual(
            self.directory.domain_for("Unknown", "Stellar Blade™"), "stellarblade"
        )
        self.assertIsNone(self.directory.domain_for("Hades"))

    def test_skips_malformed_entries(self) -> None:
        bad = [{"name": "Evil", "domain_name": "../x"}, "junk", *GAMES]
        directory = parse_game_directory(bad)
        self.assertIsNone(directory.domain_for("Evil"))
        self.assertEqual(directory.domain_for("Stellar Blade"), "stellarblade")

    def test_rejects_a_non_list(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected a list"):
            parse_game_directory({"games": []})


class LoadDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cache = Path(self.temporary.name) / "cache/nexus_games.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _cache(self, games: object, age: float) -> float:
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text(json.dumps(games))
        mtime = self.cache.stat().st_mtime
        return mtime + age

    def test_fetches_and_caches_when_missing(self) -> None:
        transport = FakeNexusGamesTransport(GAMES)
        directory = load_game_directory(self.cache, NexusApi(transport, "k"), 0.0)
        self.assertEqual(directory.domain_for("Stellar Blade"), "stellarblade")
        self.assertTrue(transport.requests[0].endswith("/games.json"))
        self.assertEqual(json.loads(self.cache.read_text()), GAMES)

    def test_fresh_cache_skips_nexus(self) -> None:
        now = self._cache(GAMES, 60)
        transport = FakeNexusGamesTransport([])
        load_game_directory(self.cache, NexusApi(transport, "k"), now)
        self.assertEqual(transport.requests, [])

    def test_offline_falls_back_to_stale_cache(self) -> None:
        now = self._cache(GAMES, CACHE_MAX_AGE_SECONDS + 1)
        transport = FakeNexusGamesTransport([], OSError("offline"))
        directory = load_game_directory(self.cache, NexusApi(transport, "k"), now)
        self.assertEqual(directory.domain_for("Kingdom Hearts III"), "kingdomhearts3")

    def test_no_key_and_no_cache_matches_nothing(self) -> None:
        self.assertEqual(
            load_game_directory(self.cache, None, 0.0), NexusGameDirectory({})
        )

    def test_corrupt_cache_matches_nothing(self) -> None:
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text("{not json")
        os.utime(self.cache, (0, 0))
        self.assertEqual(load_game_directory(self.cache, None, 1.0).domains, {})


if __name__ == "__main__":
    unittest.main()
