"""Detect installed Unreal games and treat them like built-in pak games."""

from argparse import Namespace
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from rich.console import Console

from omamods.detected_games import (
    DETECTED_GAMES_FILE,
    load_detected_games,
    parse_detected_game,
    save_detected_games,
)
from omamods.game_shelf import CATALOG, LIBRARY, MOD_READY, GameShelf, ShelfEntry
from omamods.host_cli import SteamPaksLocator
from omamods.installed_games import InstalledGame
from omamods.manifests import GameManifest
from omamods.nexus_cli import CatalogSources
from omamods.nexus_config import UserSettings
from omamods.nexus_games import NexusGameDirectory
from omamods.nexus_workflow import scanned_game_paks
from omamods.pak_detection import (
    promote_unreal_games,
    scanned_pak_game,
    scanned_pak_games,
)
from omamods.pak_games import (
    IOSTORE_SUFFIXES,
    PAK_SUFFIXES,
    PakGameCatalog,
    pak_overlay_game,
)
from omamods.tui.shelf_view import entry_detail, section_badge
from omamods.unreal_layout import UnrealLayout, detect_unreal_layout
from omamods.yaml_codec import SafeYamlDecoder
from tests.fakes import FakeFiles

REMNANT = Path("/g/Remnant2")
REMNANT_PAKS = REMNANT / "Remnant2/Content/Paks"
DIRECTORY = NexusGameDirectory(
    {"remnantii": "remnant2", "stellarblade": "stellarblade", "silenthill2": "sh2"}
)
IOSTORE_LAYOUT = UnrealLayout(Path("Remnant2/Content/Paks"), True, True)


def remnant_files() -> FakeFiles:
    names = ("pakchunk0-Windows.pak", "pakchunk0-Windows.utoc", "pakchunk0.sig")
    contents = {REMNANT_PAKS / name: "" for name in names}
    contents[REMNANT / "Engine/Content/Paks/engine.pak"] = ""
    return FakeFiles(contents)


def installed(name: str, path: Path = REMNANT, ready: bool = True) -> InstalledGame:
    return InstalledGame("Steam", "1282100", name, path, ready)


def library(game: InstalledGame) -> ShelfEntry:
    return ShelfEntry(f"steam:{game.app_id}", game.name, LIBRARY, (game,))


def render(renderable: object) -> str:
    console = Console(width=120, record=True, color_system=None, file=StringIO())
    console.print(renderable)
    return console.export_text()


class LayoutTests(unittest.TestCase):
    def test_finds_project_paks_and_ignores_engine(self) -> None:
        layout = detect_unreal_layout(REMNANT, remnant_files())
        self.assertEqual(layout, IOSTORE_LAYOUT)

    def test_pak_only_game_without_signatures(self) -> None:
        files = FakeFiles({Path("/g/AH/AtomicHeart/Content/Paks/a.pak"): ""})
        layout = detect_unreal_layout(Path("/g/AH"), files)
        self.assertEqual(
            layout, UnrealLayout(Path("AtomicHeart/Content/Paks"), False, False)
        )

    def test_finds_paks_one_folder_deeper_in_collections(self) -> None:
        pak = Path("/g/KH/KH 0.2/Game/Content/Paks/a.pak")
        layout = detect_unreal_layout(Path("/g/KH"), FakeFiles({pak: ""}))
        self.assertEqual(layout.paks_subpath, Path("KH 0.2/Game/Content/Paks"))

    def test_non_unreal_game_is_none(self) -> None:
        files = FakeFiles({Path("/g/Hades/Content/Game.pkg"): ""})
        self.assertIsNone(detect_unreal_layout(Path("/g/Hades"), files))


class PromotionTests(unittest.TestCase):
    def _promote(self, *entries: ShelfEntry) -> GameShelf:
        shelf = GameShelf(entries, (), ())
        return promote_unreal_games(shelf, remnant_files(), DIRECTORY)

    def test_matched_unreal_game_becomes_mod_ready(self) -> None:
        entry = self._promote(library(installed("Remnant II"))).entries[0]
        self.assertEqual(entry.section, MOD_READY)
        self.assertEqual(entry.pak_game.game_id, "remnant2")
        self.assertEqual(entry.pak_game.mods_dirname, "~mods")
        self.assertTrue(entry.pak_game.signed)

    def test_catalog_game_keeps_its_manifest_id(self) -> None:
        manifest = GameManifest("silent-hill-2", "SILENT HILL 2", "d", (), "x", (), 1)
        game = installed("SILENT HILL 2")
        entry = ShelfEntry("silent-hill-2", game.name, CATALOG, (game,), manifest)
        promoted = self._promote(entry).entries[0]
        self.assertEqual(promoted.pak_game.game_id, "silent-hill-2")
        self.assertEqual(promoted.pak_game.nexus_domain, "sh2")

    def test_unmatched_unreal_game_stays_but_is_marked(self) -> None:
        entry = self._promote(library(installed("Mystery Game"))).entries[0]
        self.assertEqual(entry.section, LIBRARY)
        self.assertEqual(entry.unreal, IOSTORE_LAYOUT)
        self.assertIsNone(entry.pak_game)

    def test_built_in_domain_is_never_claimed_twice(self) -> None:
        gog = replace(installed("Stellar Blade"), store="GOG")
        self.assertIsNone(self._promote(library(gog)).entries[0].pak_game)

    def test_incomplete_install_is_left_alone(self) -> None:
        entry = self._promote(library(installed("Remnant II", ready=False))).entries[0]
        self.assertIsNone(entry.unreal)

    def test_scanned_games_exclude_built_ins(self) -> None:
        sb = pak_overlay_game("stellar-blade")
        built_in = ShelfEntry("stellar-blade", "SB", MOD_READY, (), None, sb)
        shelf = self._promote(built_in, library(installed("Remnant II")))
        ids = [game.game_id for game in scanned_pak_games(shelf)]
        self.assertEqual(ids, ["remnant2"])

    def test_suffix_sets_follow_iostore(self) -> None:
        game = installed("Remnant II")
        iostore = scanned_pak_game("r", game, "r", IOSTORE_LAYOUT)
        legacy = scanned_pak_game(
            "r", game, "r", replace(IOSTORE_LAYOUT, iostore=False)
        )
        self.assertEqual(iostore.flat_suffix_sets, (PAK_SUFFIXES, IOSTORE_SUFFIXES))
        self.assertEqual(legacy.flat_suffix_sets, (PAK_SUFFIXES,))


def remnant_game() -> object:
    return scanned_pak_game(
        "remnant2", installed("Remnant II"), "remnant2", IOSTORE_LAYOUT
    )


class CatalogTests(unittest.TestCase):
    def test_includes_scanned_games(self) -> None:
        catalog = PakGameCatalog((remnant_game(),))
        self.assertEqual(catalog.for_domain("remnant2").game_id, "remnant2")
        self.assertEqual(len(catalog.all()), 3)

    def test_built_ins_win_over_a_scan(self) -> None:
        clash = replace(remnant_game(), game_id="cronos")
        self.assertIsNone(PakGameCatalog((clash,)).get("cronos").install_root)

    def test_unknown_id_names_the_choices(self) -> None:
        with self.assertRaisesRegex(ValueError, "game='nope': expected one of"):
            PakGameCatalog().get("nope")


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_round_trip(self) -> None:
        save_detected_games(self.root, (remnant_game(),))
        self.assertEqual(load_detected_games(self.root), (remnant_game(),))

    def test_missing_or_corrupt_file_is_empty(self) -> None:
        self.assertEqual(load_detected_games(self.root), ())
        (self.root / DETECTED_GAMES_FILE).write_text("[")
        self.assertEqual(load_detected_games(self.root), ())

    def test_unsafe_entries_are_skipped(self) -> None:
        path = save_detected_games(self.root, (remnant_game(),))
        records = json.loads(path.read_text())
        evil = dict(records[0], game_id="evil", mods_dirname="../../bin")
        path.write_text(json.dumps([evil, *records]))
        self.assertEqual(
            [g.game_id for g in load_detected_games(self.root)], ["remnant2"]
        )

    def test_rejects_relative_root_and_traversing_subpath(self) -> None:
        save_detected_games(self.root, (remnant_game(),))
        record = json.loads((self.root / DETECTED_GAMES_FILE).read_text())[0]
        with self.assertRaisesRegex(ValueError, "install_root='g'"):
            parse_detected_game(dict(record, install_root="g"))
        with self.assertRaisesRegex(ValueError, "expected a relative path"):
            parse_detected_game(dict(record, paks_subpath="../x"))
        with self.assertRaisesRegex(ValueError, r"expected \[a-z0-9\]\+"):
            parse_detected_game(dict(record, nexus_domain="a-b"))


class PaksLocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        layout = UnrealLayout(Path("Game/Content/Paks"), False, False)
        self.game = scanned_pak_game("g", installed("G", root), "g", layout)
        self.paks = root / "Game/Content/Paks"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_scanned_game_uses_its_install_root(self) -> None:
        self.paks.mkdir(parents=True)
        self.assertEqual(scanned_game_paks(self.game), self.paks)
        locator = SteamPaksLocator(
            Namespace(), CatalogSources(FakeFiles(), SafeYamlDecoder(), ())
        )
        settings = UserSettings("", Path("/store"), {}, ())
        self.assertEqual(locator(self.game, settings), self.paks)

    def test_moved_game_asks_for_a_rescan(self) -> None:
        with self.assertRaisesRegex(ValueError, "rescan with r"):
            scanned_game_paks(self.game)

    def test_built_in_game_is_not_scanned(self) -> None:
        with self.assertRaisesRegex(ValueError, "install_root=None"):
            scanned_game_paks(pak_overlay_game("cronos"))


class ShelfViewTests(unittest.TestCase):
    def test_scanned_game_card_shows_folder_and_signature_warning(self) -> None:
        game = remnant_game()
        entry = ShelfEntry(
            "remnant2", "Remnant II", MOD_READY, (installed("Remnant II"),), None, game
        )
        self.assertIn("auto-detected", section_badge(entry))
        text = render(entry_detail(entry, 0))
        self.assertIn("Remnant2/Content/Paks/~mods", text)
        self.assertIn(".sig files", text)

    def test_unmatched_unreal_card_explains_why(self) -> None:
        entry = replace(library(installed("Mystery")), unreal=IOSTORE_LAYOUT)
        self.assertEqual(section_badge(entry), "Not in the catalog")
        self.assertIn("no Nexus game page matched", render(entry_detail(entry, None)))


if __name__ == "__main__":
    unittest.main()
