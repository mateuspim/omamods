"""Plan, install, and revert Cyberpunk 2077 mods into the game folder."""

import json
from pathlib import Path
import tempfile
import unittest

from omamods.asset_plans import game_variants, plan_game_assets
from omamods.mod_plan import FilePlan, describe_plans
from omamods.nexus_api import NexusFile
from omamods.nexus_config import UserSettings
from omamods.nexus_workflow import (
    LocalArchiveRequest,
    install_local_archive,
    revert_mod_files,
)
from omamods.pak_games import PAK_OVERLAY_GAMES, PakGameCatalog
from omamods.pak_storage import revert_pak_mod
from omamods.red_archive import (
    is_red_game_path,
    plan_red_archives,
    red_archive_variants,
)
from tests.fakes import FakeArchiveReader

CYBERPUNK = PAK_OVERLAY_GAMES["cyberpunk-2077"]
RED4EXT_MEMBERS = {
    "bin/x64/winmm.dll": b"proxy",
    "red4ext/RED4ext.dll": b"loader",
    "red4ext/LICENSE.txt": b"license",
}


def targets(members: tuple[str, ...], option: str | None = None) -> list[str]:
    planned = plan_red_archives(members, CYBERPUNK, option)
    return [a.target.as_posix() for a in planned]


class CyberpunkGameTests(unittest.TestCase):
    def test_cyberpunk_is_a_builtin_game_root_game(self) -> None:
        game = PakGameCatalog().for_domain("cyberpunk2077")
        self.assertTrue(game.redengine)
        self.assertEqual(game.paks_subpath, Path("."))
        self.assertEqual(game.steam_app_id, "1091500")

    def test_folder_label_names_the_game_folder(self) -> None:
        self.assertEqual(CYBERPUNK.folder_label(), "<game>")
        self.assertEqual(PAK_OVERLAY_GAMES["cronos"].folder_label(), "Paks")


class CyberpunkLayoutTests(unittest.TestCase):
    def test_game_folders_keep_their_path(self) -> None:
        self.assertEqual(
            targets((*RED4EXT_MEMBERS, "red4ext/")),
            ["bin/x64/winmm.dll", "red4ext/LICENSE.txt", "red4ext/RED4ext.dll"],
        )

    def test_wrapping_folder_is_dropped(self) -> None:
        members = ("Cyberpunk 2077/r6/scripts/a.reds", "Cyberpunk 2077/readme.txt")
        self.assertEqual(targets(members), ["r6/scripts/a.reds"])

    def test_top_folder_case_is_normalised(self) -> None:
        # The disk is case-sensitive; Bin/ would sit beside the game's bin/.
        self.assertEqual(targets(("Bin/x64/a.asi",)), ["bin/x64/a.asi"])

    def test_loose_archive_and_xl_go_to_archive_pc_mod(self) -> None:
        members = ("Hair.archive", "Hair.archive.xl", "preview.png")
        self.assertEqual(
            targets(members),
            ["archive/pc/mod/Hair.archive", "archive/pc/mod/Hair.archive.xl"],
        )

    def test_loose_code_has_no_destination(self) -> None:
        with self.assertRaisesRegex(ValueError, "destination is unknown"):
            targets(("a.archive", "init.lua"))

    def test_redmod_and_fomod_are_refused(self) -> None:
        for member, reason in (
            ("mods/Name/info.json", "REDmod"),
            ("fomod/ModuleConfig.xml", "FOMOD"),
        ):
            with (
                self.subTest(member=member),
                self.assertRaisesRegex(ValueError, reason),
            ):
                targets(("archive/pc/mod/a.archive", member))

    def test_cet_mods_folder_is_not_redmod(self) -> None:
        # Regression: Native Settings UI (3518) was refused as a REDmod package.
        member = "bin/x64/plugins/cyber_engine_tweaks/mods/nativeSettings/init.lua"
        self.assertEqual(targets((member,)), [member])

    def test_variant_folders_are_listed_and_chosen(self) -> None:
        members = ("Black/archive/pc/mod/s.archive", "White/s.archive")
        self.assertEqual(red_archive_variants(members, CYBERPUNK), ("Black", "White"))
        self.assertEqual(targets(members, "White"), ["archive/pc/mod/s.archive"])
        with self.assertRaisesRegex(ValueError, "expected one variant"):
            targets(members)

    def test_unknown_option_names_the_folders(self) -> None:
        with self.assertRaisesRegex(ValueError, r"from \['A'\]"):
            targets(("A/a.archive",), "B")

    def test_paths_differing_only_in_case_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "ignoring case"):
            targets(("archive/pc/mod/X.archive", "x.archive"))

    def test_archive_without_game_files_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected .archive files"):
            targets(("readme.txt",))

    def test_engine_dispatch_uses_the_redengine_planner(self) -> None:
        members = ("A/a.archive", "B/a.archive")
        self.assertEqual(game_variants(members, CYBERPUNK), ("A", "B"))
        planned = plan_game_assets(members, CYBERPUNK, "B")
        self.assertEqual([a.member for a in planned], ["B/a.archive"])

    def test_plan_description_shows_the_game_folder(self) -> None:
        planned = plan_red_archives(("a.archive",), CYBERPUNK, None)
        plan = FilePlan(NexusFile(1, "Hair.zip", "MAIN", 0), None, planned)
        self.assertEqual(
            describe_plans((plan,), CYBERPUNK.folder_label()),
            "Hair.zip\n  <game>/archive/pc/mod/a.archive",
        )

    def test_owned_paths_must_sit_in_a_game_folder(self) -> None:
        self.assertTrue(is_red_game_path("bin/x64/winmm.dll"))
        for path in ("winmm.dll", "/bin/x", "bin/../x", "mods/a/b", "Cyberpunk.exe"):
            with self.subTest(path=path):
                self.assertFalse(is_red_game_path(path))


class CyberpunkInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.game_root = base / "Cyberpunk 2077"
        (self.game_root / "bin" / "x64").mkdir(parents=True)
        (self.game_root / "bin/x64/Cyberpunk2077.exe").write_bytes(b"game")
        self.settings = UserSettings("", base / "storage", {}, ())
        self.source = base / "RED4ext.zip"
        self.source.write_bytes(b"zip")
        self.reader = FakeArchiveReader(dict(RED4EXT_MEMBERS))

    def _install(self) -> int:
        request = LocalArchiveRequest(self.source, 2380, 70, None)
        _, count = install_local_archive(
            CYBERPUNK, self.settings, self.game_root, request, self.reader
        )
        return count

    def test_install_writes_game_files_and_revert_prunes_folders(self) -> None:
        self.assertEqual(self._install(), 3)
        self.assertEqual((self.game_root / "bin/x64/winmm.dll").read_bytes(), b"proxy")
        self.assertEqual(
            revert_mod_files(CYBERPUNK, self.settings.storage_root, 2380, 70), 3
        )
        self.assertFalse((self.game_root / "red4ext").exists())
        self.assertTrue((self.game_root / "bin/x64/Cyberpunk2077.exe").is_file())

    def test_emptied_shipped_top_folder_stays(self) -> None:
        self._install()
        (self.game_root / "bin/x64/Cyberpunk2077.exe").unlink()
        revert_mod_files(CYBERPUNK, self.settings.storage_root, 2380, 70)
        self.assertTrue((self.game_root / "bin").is_dir())

    def test_empty_marker_files_install_and_revert(self) -> None:
        # Regression: ArchiveXL 1.27.4 ships a 0-byte ArchiveXL.toml, and the
        # empty-file check for paks refused the whole archive.
        self.reader.contents["r6/config/redsUserHints/ArchiveXL.toml"] = b""
        self.assertEqual(self._install(), 4)
        marker = self.game_root / "r6/config/redsUserHints/ArchiveXL.toml"
        self.assertEqual(marker.read_bytes(), b"")
        revert_mod_files(CYBERPUNK, self.settings.storage_root, 2380, 70)
        self.assertFalse(marker.exists())

    def test_failed_install_removes_the_folders_it_made(self) -> None:
        class BrokenReader(FakeArchiveReader):
            def copy_member(self, archive, member, destination) -> None:
                if member.startswith("red4ext/RED4ext"):
                    raise ValueError(f"archive member={member!r}: expected a file")
                super().copy_member(archive, member, destination)

        self.reader = BrokenReader(dict(RED4EXT_MEMBERS))
        with self.assertRaisesRegex(ValueError, "expected a file"):
            self._install()
        self.assertFalse((self.game_root / "red4ext").exists())
        self.assertFalse((self.game_root / "bin/x64/winmm.dll").exists())
        self.assertTrue((self.game_root / "bin/x64").is_dir())

    def test_existing_game_file_is_never_overwritten(self) -> None:
        (self.game_root / "bin/x64/winmm.dll").write_bytes(b"theirs")
        with self.assertRaisesRegex(ValueError, "expected an unowned path"):
            self._install()

    def test_revert_refuses_a_record_owning_a_root_file(self) -> None:
        self._install()
        record = next((self.settings.storage_root / "state").rglob("*.json"))
        state = json.loads(record.read_text())
        state["assets"][0]["relative_path"] = "Cyberpunk2077.exe"
        record.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "beneath a game folder"):
            revert_pak_mod(record, CYBERPUNK)


if __name__ == "__main__":
    unittest.main()
