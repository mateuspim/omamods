"""Detect RE Engine games and install their pak mods as numbered patches."""

from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from rich.console import Console

from omamods.asset_plans import game_variants, plan_game_assets
from omamods.detected_games import (
    load_detected_games,
    parse_detected_game,
    save_detected_games,
)
from omamods.game_shelf import LIBRARY, MOD_READY, GameShelf, ShelfEntry
from omamods.installed_games import InstalledGame
from omamods.mod_plan import FilePlan, conflicting_targets, describe_plans
from omamods.nexus_api import NexusFile
from omamods.nexus_config import UserSettings
from omamods.nexus_games import NexusGameDirectory
from omamods.nexus_workflow import (
    LocalArchiveRequest,
    install_local_archive,
    revert_mod_files,
)
from omamods.pak_archive import PlannedAsset
from omamods.pak_detection import promote_pak_games, scanned_pak_games
from omamods.pak_games import PakOverlayGame, pak_overlay_game
from omamods.pak_storage import revert_pak_mod
from omamods.re_engine_detection import re_engine_domain, scanned_re_engine_game
from omamods.re_engine_layout import BASE_PAK, SUB_PAK, detect_patch_chain
from omamods.re_pak_archive import patch_pak_variants, plan_patch_paks
from omamods.re_patch_chain import (
    fill_patch_gaps,
    free_patch_numbers,
    is_empty_patch,
    number_patches,
    patch_name,
    patch_number,
)
from omamods.tui.shelf_view import entry_detail, section_badge
from tests.fakes import FakeArchiveReader, FakeFiles

RE7 = Path("/g/RE7")
V4_HEADER = b"KPKA\x04\x00\x00\x00" + bytes(8)
DIRECTORY = NexusGameDirectory({"residentevil4": "residentevil4", "mhw": "wilds"})


def re7_install(
    app_id: str = "418370", name: str = "Resident Evil 7 Biohazard"
) -> InstalledGame:
    return InstalledGame("Steam", app_id, name, RE7, True)


def re7_files() -> FakeFiles:
    names = (BASE_PAK, f"{BASE_PAK}.patch_002.pak", "dlc/re_dlc_000.pak")
    return FakeFiles({RE7 / name: "" for name in names})


def re7_game() -> PakOverlayGame:
    return scanned_re_engine_game("re7", re7_install(), "residentevil7", BASE_PAK)


def library(game: InstalledGame) -> ShelfEntry:
    return ShelfEntry(f"steam:{game.app_id}", game.name, LIBRARY, (game,))


def render(renderable: object) -> str:
    console = Console(width=200, record=True, color_system=None, file=StringIO())
    console.print(renderable)
    return console.export_text()


class LayoutTests(unittest.TestCase):
    def test_base_pak_is_the_chain(self) -> None:
        self.assertEqual(detect_patch_chain(RE7, re7_files()), BASE_PAK)

    def test_sub_pak_wins_when_present(self) -> None:
        files = FakeFiles({RE7 / BASE_PAK: "", RE7 / SUB_PAK: ""})
        self.assertEqual(detect_patch_chain(RE7, files), SUB_PAK)

    def test_other_games_have_no_chain(self) -> None:
        files = FakeFiles({RE7 / "Game/Content/Paks/a.pak": ""})
        self.assertIsNone(detect_patch_chain(RE7, files))


class DomainTests(unittest.TestCase):
    def test_remake_is_pinned_by_steam_app_id(self) -> None:
        game = re7_install("2050650", "Resident Evil 4")
        found = re_engine_domain(game, ("Resident Evil 4",), DIRECTORY)
        self.assertEqual(found, "residentevil42023")

    def test_other_games_match_by_title(self) -> None:
        game = re7_install("2246340", "MHW")
        self.assertEqual(re_engine_domain(game, ("MHW",), DIRECTORY), "wilds")

    def test_pin_is_steam_only(self) -> None:
        game = replace(re7_install("2050650", "Resident Evil 4"), store="GOG")
        found = re_engine_domain(game, ("Resident Evil 4",), DIRECTORY)
        self.assertEqual(found, "residentevil4")


class PromotionTests(unittest.TestCase):
    def _promote(self, game: InstalledGame) -> ShelfEntry:
        shelf = GameShelf((library(game),), (), ())
        return promote_pak_games(shelf, re7_files(), DIRECTORY).entries[0]

    def test_re7_becomes_mod_ready(self) -> None:
        entry = self._promote(re7_install())
        self.assertEqual(entry.section, MOD_READY)
        self.assertEqual(entry.pak_game.nexus_domain, "residentevil7")
        self.assertEqual(entry.pak_game.patch_chain, BASE_PAK)
        self.assertEqual(entry.pak_game.install_root, RE7)

    def test_unmatched_game_is_marked(self) -> None:
        entry = self._promote(re7_install("1", "Mystery"))
        self.assertEqual(entry.section, LIBRARY)
        self.assertEqual(entry.patch_chain, BASE_PAK)
        self.assertIsNone(entry.pak_game)

    def test_scanned_games_include_re_engine(self) -> None:
        shelf = GameShelf((library(re7_install()),), (), ())
        promoted = promote_pak_games(shelf, re7_files(), DIRECTORY)
        self.assertEqual(
            [g.game_id for g in scanned_pak_games(promoted)], ["residentevil7"]
        )


class PlanTests(unittest.TestCase):
    def test_fluffy_archive_queues_its_pak(self) -> None:
        members = ("Mod/modinfo.ini", "Mod/cover.png", "Mod/my.pak")
        planned = plan_patch_paks(members, re7_game(), None)
        self.assertEqual(planned, (PlannedAsset("Mod/my.pak", Path("my.pak"), True),))

    def test_several_paks_keep_name_order(self) -> None:
        planned = plan_patch_paks(("b.pak", "a.pak"), re7_game(), None)
        self.assertEqual([a.member for a in planned], ["a.pak", "b.pak"])

    def test_reframework_scripts_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "REFramework"):
            plan_patch_paks(("reframework/autorun/a.txt",), re7_game(), None)

    def test_loader_dll_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "loaders"):
            plan_patch_paks(("dinput8.dll", "a.pak"), re7_game(), None)

    def test_archive_without_paks_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected .pak patches"):
            plan_patch_paks(("readme.txt",), re7_game(), None)

    def test_variants_need_a_choice(self) -> None:
        members = ("Red/a.pak", "Blue/a.pak")
        self.assertEqual(patch_pak_variants(members), ("Blue", "Red"))
        with self.assertRaisesRegex(ValueError, "one variant"):
            plan_patch_paks(members, re7_game(), None)
        chosen = plan_patch_paks(members, re7_game(), "Red")
        self.assertEqual([a.member for a in chosen], ["Red/a.pak"])

    def test_single_folder_has_no_variants(self) -> None:
        self.assertEqual(patch_pak_variants(("Mod/a.pak",)), ())

    def test_dispatch_follows_the_engine(self) -> None:
        unreal = pak_overlay_game("stellar-blade")
        members = ("Red/a.pak", "Blue/a.pak")
        self.assertTrue(plan_game_assets(("a.pak",), re7_game(), None)[0].next_patch)
        self.assertFalse(plan_game_assets(("a.pak",), unreal, None)[0].next_patch)
        self.assertEqual(game_variants(members, re7_game()), ("Blue", "Red"))
        self.assertEqual(game_variants(members, unreal), ("Blue", "Red"))


class PreviewTests(unittest.TestCase):
    def _plan(self, file_id: int) -> FilePlan:
        file = NexusFile(file_id, f"f{file_id}.zip", "MAIN", 0)
        return FilePlan(file, None, (PlannedAsset("a.pak", Path("a.pak"), True),))

    def test_patches_never_conflict(self) -> None:
        self.assertEqual(conflicting_targets((self._plan(1), self._plan(2))), ())

    def test_preview_names_the_patch_slot(self) -> None:
        text = describe_plans((self._plan(1),))
        self.assertIn("next free patch_NNN.pak <- a.pak", text)


class ChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def _touch(self, *numbers: int) -> None:
        for number in numbers:
            (self.root / patch_name(BASE_PAK, number)).write_bytes(bytes(32))

    def test_names_round_trip(self) -> None:
        name = patch_name(BASE_PAK, 9)
        self.assertEqual(name, "re_chunk_000.pak.patch_009.pak")
        self.assertEqual(patch_number(BASE_PAK, name), 9)
        self.assertIsNone(patch_number(SUB_PAK, name))
        self.assertIsNone(patch_number(BASE_PAK, "../" + name))

    def test_free_numbers_fill_the_lowest_gaps(self) -> None:
        # RE7's layout: patch_002..008 but no patch_001, which the chain needs.
        self.assertEqual(free_patch_numbers(self.root, BASE_PAK, 1), (1,))
        self._touch(2, 3, 4, 5, 6, 7, 8)
        self.assertEqual(free_patch_numbers(self.root, BASE_PAK, 2), (1, 9))

    def test_empty_patches_are_free_slots(self) -> None:
        (self.root / patch_name(BASE_PAK, 1)).write_bytes(bytes(32))
        (self.root / patch_name(BASE_PAK, 2)).write_bytes(b"")
        (self.root / patch_name(BASE_PAK, 3)).write_bytes(V4_HEADER)
        self.assertEqual(free_patch_numbers(self.root, BASE_PAK, 3), (2, 3, 4))
        planned = (PlannedAsset("a", Path("a.pak"), True),) * 3
        replaced = [
            a.replaces_empty for a in number_patches(planned, self.root, BASE_PAK)
        ]
        self.assertEqual(replaced, [True, True, False])

    def test_only_file_less_patches_are_empty(self) -> None:
        for content, empty in ((b"", True), (V4_HEADER, True), (b"x" * 16, False)):
            (self.root / "p.pak").write_bytes(content)
            self.assertEqual(is_empty_patch(self.root / "p.pak"), empty, content)
        self.assertFalse(is_empty_patch(self.root / "missing.pak"))

    def test_numbering_is_sequential(self) -> None:
        self._touch(3)
        planned = (PlannedAsset("a", Path("a.pak"), True),) * 2
        numbered = number_patches(planned, self.root, BASE_PAK)
        self.assertEqual(
            [a.target.name for a in numbered],
            [patch_name(BASE_PAK, 1), patch_name(BASE_PAK, 2)],
        )
        self.assertFalse(any(a.next_patch for a in numbered))

    def test_numbering_stops_at_999(self) -> None:
        planned = (PlannedAsset("a", Path("a.pak"), True),) * 1000
        with self.assertRaisesRegex(ValueError, "free patch numbers=999"):
            number_patches(planned, self.root, BASE_PAK)

    def test_gap_below_a_patch_gets_a_placeholder(self) -> None:
        self._touch(3)
        removed = (
            self.root / patch_name(BASE_PAK, 1),
            self.root / patch_name(BASE_PAK, 2),
        )
        self.assertEqual(fill_patch_gaps(removed, BASE_PAK), tuple(reversed(removed)))
        self.assertEqual(removed[0].read_bytes(), V4_HEADER)

    def test_top_of_chain_needs_no_placeholder(self) -> None:
        self._touch(1)
        removed = (self.root / patch_name(BASE_PAK, 2),)
        self.assertEqual(fill_patch_gaps(removed, BASE_PAK), ())
        self.assertFalse(removed[0].exists())


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.game_root = base / "RE7"
        self.game_root.mkdir()
        (self.game_root / BASE_PAK).write_bytes(V4_HEADER)
        (self.game_root / patch_name(BASE_PAK, 2)).write_bytes(b"")
        self.settings = UserSettings("", base / "storage", {}, ())
        self.game = replace(re7_game(), install_root=self.game_root)
        self.source = base / "mod.zip"
        self.source.write_bytes(b"zip")

    def _install(self, file_id: int, contents: bytes) -> None:
        reader = FakeArchiveReader({"Mod/modinfo.ini": b"", "Mod/a.pak": contents})
        request = LocalArchiveRequest(self.source, 5, file_id, None)
        install_local_archive(self.game, self.settings, self.game_root, request, reader)

    def _patch(self, number: int) -> Path:
        return self.game_root / patch_name(BASE_PAK, number)

    def test_install_fills_the_missing_first_patch(self) -> None:
        self._install(1, b"mod")
        self.assertEqual(self._patch(1).read_bytes(), b"mod")
        # Capcom's 0-byte patch_002 stops the chain, so the mod takes its slot.
        self._install(2, b"two")
        self.assertEqual(self._patch(2).read_bytes(), b"two")

    def test_revert_of_the_top_patch_removes_it(self) -> None:
        self._install(1, b"mod")
        self.assertEqual(
            revert_mod_files(self.game, self.settings.storage_root, 5, 1), 1
        )
        # Capcom's empty patch_002 above needs no placeholder below it.
        self.assertFalse(self._patch(1).exists())
        self.assertEqual(self._patch(2).read_bytes(), b"")

    def test_revert_below_another_mod_keeps_the_chain(self) -> None:
        self._install(1, b"one")
        self._install(2, b"two" * 20)
        revert_mod_files(self.game, self.settings.storage_root, 5, 1)
        self.assertEqual(self._patch(1).read_bytes(), V4_HEADER)
        self.assertEqual(self._patch(2).read_bytes(), b"two" * 20)

    def test_revert_puts_capcoms_empty_patch_back(self) -> None:
        self._install(1, b"one")
        self._install(2, b"two")
        revert_mod_files(self.game, self.settings.storage_root, 5, 2)
        self.assertEqual(self._patch(2).read_bytes(), b"")
        self.assertEqual(self._patch(1).read_bytes(), b"one")

    def test_failed_install_puts_the_empty_patch_back(self) -> None:
        self._install(1, b"one")
        with self.assertRaisesRegex(ValueError, "nonempty content"):
            self._install(2, b"")
        self.assertEqual(self._patch(2).read_bytes(), b"")

    def test_record_outside_the_chain_is_refused(self) -> None:
        record = self.settings.storage_root / "bad.json"
        record.parent.mkdir(parents=True)
        asset = {"relative_path": "re7.exe", "sha256": "0" * 64}
        state = {"paks": str(self.game_root), "assets": [asset]}
        record.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "patch_NNN"):
            revert_pak_mod(record, self.game)
        self.assertTrue(record.exists())


class SavedGameTests(unittest.TestCase):
    def test_round_trip_keeps_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            save_detected_games(Path(temp), (re7_game(),))
            self.assertEqual(load_detected_games(Path(temp)), (re7_game(),))

    def _record(self) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temp:
            path = save_detected_games(Path(temp), (re7_game(),))
            return json.loads(path.read_text(encoding="utf-8"))[0]

    def test_unknown_chain_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "patch_chain"):
            parse_detected_game(dict(self._record(), patch_chain="../re7.exe"))

    def test_re_engine_mods_folder_must_be_empty(self) -> None:
        with self.assertRaisesRegex(ValueError, "mods_dirname"):
            parse_detected_game(dict(self._record(), mods_dirname="mods"))


class CardTests(unittest.TestCase):
    def test_mod_ready_card_explains_patches(self) -> None:
        entry = ShelfEntry("re7", "RE7", MOD_READY, (re7_install(),), None, re7_game())
        self.assertEqual(
            section_badge(entry), "Mod-ready (auto-detected RE Engine game)"
        )
        text = render(entry_detail(entry, None))
        self.assertIn("next re_chunk_000.pak.patch_NNN.pak", text)
        self.assertIn("game update", text)

    def test_unmatched_card_explains_why(self) -> None:
        entry = replace(library(re7_install()), patch_chain=BASE_PAK)
        text = render(entry_detail(entry, None))
        self.assertIn("RE Engine game, but no Nexus game page matched", text)


if __name__ == "__main__":
    unittest.main()
