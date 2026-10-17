"""Plan, install, and revert ASI plugin archives such as MGSVFix."""

from pathlib import Path
import tempfile
import unittest

from omamods.asi_archive import (
    asi_loaders_on_disk,
    is_asi_archive,
    is_asi_game_path,
    is_removable_asi_folder,
    plan_asi_bundle,
)
from omamods.asset_plans import game_variants, plan_game_assets
from omamods.launch_options_advice import launch_options_advice
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.pak_storage import install_pak_archive, revert_pak_mod
from omamods.red_frameworks import launch_options_hint
from tests.fakes import FakeArchiveReader

MGSV = PAK_OVERLAY_GAMES["metalgearsolidvtpp"]
# MGSVFix 0.0.3's zip, as listed by bsdtar.
MGSVFIX_MEMBERS = ("EXTRACT_TO_GAME_FOLDER", "MGSVFix.asi", "MGSVFix.ini", "winmm.dll")


def targets(members: tuple[str, ...]) -> dict[str, str]:
    return {a.member: a.target.as_posix() for a in plan_asi_bundle(members, MGSV)}


class PlanTests(unittest.TestCase):
    def test_mgsvfix_goes_beside_the_executable(self) -> None:
        planned = plan_asi_bundle(MGSVFIX_MEMBERS, MGSV)
        self.assertEqual(
            {a.target.as_posix(): a.user_editable for a in planned},
            {"MGSVFix.asi": False, "MGSVFix.ini": True, "winmm.dll": False},
        )

    def test_a_wrapping_folder_is_dropped(self) -> None:
        found = targets(("MGSVFix/MGSVFix.asi", "MGSVFix/WINMM.dll", "MGSVFix/"))
        self.assertEqual(
            found,
            {"MGSVFix/MGSVFix.asi": "MGSVFix.asi", "MGSVFix/WINMM.dll": "winmm.dll"},
        )

    def test_scripts_folder_keeps_its_place(self) -> None:
        found = targets(("dinput8.dll", "scripts/Fix.asi", "scripts/Fix.ini"))
        self.assertEqual(found["scripts/Fix.asi"], "scripts/Fix.asi")
        self.assertEqual(found["dinput8.dll"], "dinput8.dll")

    def test_the_loader_is_optional(self) -> None:
        self.assertEqual(targets(("Fix.asi",)), {"Fix.asi": "Fix.asi"})

    def test_snakebite_packages_are_refused_by_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "SnakeBite"):
            plan_asi_bundle(("Mod.mgsv", "readme.txt"), MGSV)

    def test_unknown_dlls_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "other.dll"):
            plan_asi_bundle(("Fix.asi", "other.dll"), MGSV)

    def test_case_clashes_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "ignoring case"):
            plan_asi_bundle(("scripts/Fix.asi", "Scripts/fix.asi"), MGSV)

    def test_asi_games_route_to_this_planner(self) -> None:
        planned = plan_game_assets(MGSVFIX_MEMBERS, MGSV, None)
        self.assertEqual(len(planned), 3)
        self.assertEqual(game_variants(MGSVFIX_MEMBERS, MGSV), ())
        self.assertTrue(is_asi_archive(MGSVFIX_MEMBERS))
        self.assertEqual(MGSV.folder_label(), "<game>")


class OwnedPathTests(unittest.TestCase):
    def test_accepts_plugins_loaders_and_plugin_folders(self) -> None:
        for path in ("MGSVFix.asi", "MGSVFix.ini", "winmm.dll", "plugins/A.asi"):
            self.assertTrue(is_asi_game_path(path), path)

    def test_refuses_game_files_and_traversal(self) -> None:
        for path in ("mgsvtpp.exe", "master/0/00.dat", "../x.asi", "/x.asi", "a/b.asi"):
            self.assertFalse(is_asi_game_path(path), path)


class DiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "MGS_TPP"
        self.root.mkdir()
        self.record = Path(self.temporary.name) / "state/1/9001.json"
        self.archive = Path(self.temporary.name) / "MGSVFix.zip"
        self.archive.write_bytes(b"zip")

    def _install(self, members: dict[str, bytes]) -> None:
        reader = FakeArchiveReader(members)
        planned = plan_asi_bundle(tuple(members), MGSV)
        install_pak_archive(self.archive, self.root, self.record, 9001, reader, planned)

    def test_install_and_revert_round_trip_keeps_game_files(self) -> None:
        (self.root / "mgsvtpp.exe").write_bytes(b"game")
        self._install({"MGSVFix.asi": b"asi", "MGSVFix.ini": b"[a]", "winmm.dll": b"l"})
        (self.root / "MGSVFix.ini").write_bytes(b"[edited]")  # Edited by hand.
        removed = revert_pak_mod(self.record, MGSV)
        self.assertEqual(len(removed), 3)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["mgsvtpp.exe"])

    def test_revert_prunes_emptied_scripts_folder(self) -> None:
        self._install({"scripts/Fix.asi": b"asi"})
        revert_pak_mod(self.record, MGSV)
        self.assertFalse((self.root / "scripts").exists())

    def test_existing_loader_blocks_the_install(self) -> None:
        (self.root / "winmm.dll").write_bytes(b"another mod's")
        with self.assertRaisesRegex(ValueError, "winmm.dll"):
            self._install({"Fix.asi": b"asi", "winmm.dll": b"loader"})

    def test_loaders_on_disk_and_removable_folders(self) -> None:
        (self.root / "winmm.dll").write_bytes(b"loader")
        (self.root / "scripts").mkdir()
        self.assertEqual(asi_loaders_on_disk(self.root, Path.exists), {"winmm"})
        self.assertTrue(is_removable_asi_folder(self.root, self.root / "scripts"))
        self.assertFalse(is_removable_asi_folder(self.root, self.root))


class LaunchHintTests(unittest.TestCase):
    def test_hint_names_the_asi_loader_not_red4ext(self) -> None:
        hint = launch_options_hint(("winmm",), "ASI loader")
        self.assertIn("ASI loader mods do nothing", hint)
        self.assertNotIn("RED4ext", hint)

    def test_advice_adds_the_winmm_override(self) -> None:
        advice = launch_options_advice(
            ("%command%",), frozenset(), None, "287700", frozenset({"winmm"})
        )
        self.assertEqual(advice.suggested, 'WINEDLLOVERRIDES="winmm=n,b" %command%')


if __name__ == "__main__":
    unittest.main()
