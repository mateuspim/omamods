"""Find installed Steam and Heroic games from launcher records, via fake files."""

import json
from pathlib import Path
import unittest

from omamods.heroic_games import (
    HEROIC_RECORDS,
    default_heroic_roots,
    heroic_game,
    list_heroic_games,
)
from omamods.installed_games import InstalledGame, InstalledScan, combine_scans
from omamods.steam_apps import build_id, proton_prefix, steam_marks_installed
from omamods.steam_installed import is_steam_tool, list_steam_games, steam_game
from omamods.steam_libraries import LibraryScan
from tests.fakes import FakeFiles

LIBRARY = Path("/games/SteamLibrary")
HEROIC = Path("/home/me/.config/heroic")


def app_manifest(app_id: int, name: str, folder: str, flags: str = "4") -> str:
    return (
        '"AppState"\n{\n'
        f'"appid" "{app_id}"\n"name" "{name}"\n"installdir" "{folder}"\n'
        f'"StateFlags" "{flags}"\n"SizeOnDisk" "2000000000"\n"buildid" "77"\n}}\n'
    )


def manifest_path(app_id: int) -> Path:
    return LIBRARY / f"steamapps/appmanifest_{app_id}.acf"


class SteamManifestHelperTests(unittest.TestCase):
    def test_build_id_is_optional(self) -> None:
        self.assertEqual(build_id({"buildid": "12"}), "12")
        self.assertIsNone(build_id({}))

    def test_state_flag_four_means_installed(self) -> None:
        self.assertTrue(steam_marks_installed({"StateFlags": "1030"}))
        self.assertFalse(steam_marks_installed({"StateFlags": "2"}))

    def test_proton_prefix_only_when_present(self) -> None:
        prefix = LIBRARY / "steamapps/compatdata/5/pfx"
        self.assertEqual(proton_prefix(LIBRARY, 5, FakeFiles({}, (prefix,))), prefix)
        self.assertIsNone(proton_prefix(LIBRARY, 5, FakeFiles()))


class SteamInstalledTests(unittest.TestCase):
    def test_tools_are_not_games(self) -> None:
        for name in ("Proton 9.0", "Proton Experimental", "Steam Linux Runtime 3.0"):
            self.assertTrue(is_steam_tool(name), name)
        self.assertTrue(is_steam_tool("Steamworks Common Redistributables"))
        self.assertFalse(is_steam_tool("Protonix Saga"))

    def test_steam_game_reads_fields_and_folder(self) -> None:
        folder = LIBRARY / "steamapps/common/SB"
        fields = {"appid": "9", "name": " SB ", "installdir": "SB", "StateFlags": "4"}
        game = steam_game(fields, LIBRARY, FakeFiles({}, (folder,)))
        self.assertEqual((game.app_id, game.name, game.ready), ("9", "SB", True))
        self.assertEqual(game.install_path, folder)
        self.assertIsNone(game.size_bytes)

    def test_lists_games_skips_tools_and_reports_bad_manifests(self) -> None:
        files = FakeFiles(
            {
                manifest_path(1): app_manifest(1, "Hades", "Hades"),
                manifest_path(2): app_manifest(2, "Proton 9.0", "Proton 9.0"),
                manifest_path(3): '"AppState"\n{\n"appid" "3"\n}\n',
            },
            (LIBRARY / "steamapps/common/Hades",),
        )
        found = list_steam_games(LibraryScan((LIBRARY,), ()), files)
        self.assertEqual([g.name for g in found.games], ["Hades"])
        self.assertEqual(found.games[0].size_bytes, 2_000_000_000)
        self.assertEqual(found.games[0].build_id, "77")
        self.assertEqual(len(found.warnings), 1)
        self.assertIn("appmanifest_3.acf", found.warnings[0])

    def test_unfinished_install_is_not_ready(self) -> None:
        files = FakeFiles({manifest_path(1): app_manifest(1, "Hades", "Hades", "6")})
        game = list_steam_games(LibraryScan((LIBRARY,), ()), files).games[0]
        self.assertFalse(game.ready)


class HeroicTests(unittest.TestCase):
    def test_default_roots_cover_native_and_flatpak(self) -> None:
        home = Path("/home/me")
        roots = default_heroic_roots(home, "relative")
        self.assertEqual(roots[0], HEROIC)
        self.assertIn("com.heroicgameslauncher.hgl", str(roots[1]))
        self.assertEqual(default_heroic_roots(home, "/xdg")[0], Path("/xdg/heroic"))

    def test_heroic_game_falls_back_to_folder_name(self) -> None:
        entry = {"appName": "12", "install_path": "/games/Hades II"}
        game = heroic_game(entry, HEROIC_RECORDS[1], FakeFiles())
        self.assertEqual(
            (game.store, game.name, game.ready), ("GOG", "Hades II", False)
        )

    def test_heroic_game_rejects_relative_paths(self) -> None:
        entry = {"appName": "12", "install_path": "games/Hades"}
        with self.assertRaisesRegex(ValueError, "expected an absolute path"):
            heroic_game(entry, HEROIC_RECORDS[1], FakeFiles())

    def test_reads_every_store_and_skips_dlc(self) -> None:
        epic = {
            "Fortnite": {
                "app_name": "Fortnite",
                "title": "Fortnite",
                "install_path": "/games/Fortnite",
                "install_size": 5,
            },
            "Dlc": {"app_name": "Dlc", "install_path": "/games/Dlc", "is_dlc": True},
        }
        gog = {"installed": [{"appName": "1", "install_path": "/games/Gwent"}]}
        nile = [{"id": "amz", "path": "/games/Amazon Game"}]
        sideload = {
            "games": [
                {
                    "app_name": "s",
                    "title": "Mine",
                    "folder_name": "/g/Mine",
                    "is_installed": True,
                },
                {
                    "app_name": "t",
                    "title": "Gone",
                    "folder_name": "/g/Gone",
                    "is_installed": False,
                },
            ]
        }
        files = FakeFiles(
            {
                HEROIC / "legendaryConfig/legendary/installed.json": json.dumps(epic),
                HEROIC / "gog_store/installed.json": json.dumps(gog),
                HEROIC / "nile_config/nile/installed.json": json.dumps(nile),
                HEROIC / "sideload_apps/library.json": json.dumps(sideload),
            },
            (HEROIC, Path("/games/Fortnite")),
        )
        found = list_heroic_games((HEROIC, Path("/missing")), files)
        names = {(g.store, g.name, g.ready) for g in found.games}
        self.assertEqual(
            names,
            {
                ("Epic", "Fortnite", True),
                ("GOG", "Gwent", False),
                ("Amazon", "Amazon Game", False),
                ("Sideloaded", "Mine", False),
            },
        )
        self.assertEqual(found.warnings, ())

    def test_broken_record_becomes_a_warning(self) -> None:
        files = FakeFiles({HEROIC / "gog_store/installed.json": "{nope"}, (HEROIC,))
        found = list_heroic_games((HEROIC,), files)
        self.assertEqual(found.games, ())
        self.assertIn("gog_store/installed.json", found.warnings[0])

    def test_wrong_shape_names_the_value(self) -> None:
        files = FakeFiles({HEROIC / "gog_store/installed.json": "[1]"}, (HEROIC,))
        warning = list_heroic_games((HEROIC,), files).warnings[0]
        self.assertIn("expected {'installed': [...]}", warning)


class CombineScansTests(unittest.TestCase):
    def test_keeps_games_and_warnings_in_order(self) -> None:
        one = InstalledGame("Steam", "1", "A", Path("/a"), True)
        two = InstalledGame("GOG", "2", "B", Path("/b"), True)
        merged = combine_scans(
            InstalledScan((one,), ("w1",)), InstalledScan((two,), ("w2",))
        )
        self.assertEqual(merged, InstalledScan((one, two), ("w1", "w2")))


if __name__ == "__main__":
    unittest.main()
