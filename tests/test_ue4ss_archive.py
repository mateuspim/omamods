"""Plan, install, and revert Unreal mods that bundle UE4SS beside the exe."""

import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from omamods.asset_plans import game_variants, plan_game_assets
from omamods.launch_options_advice import launch_options_advice
from omamods.mod_plan import FilePlan, describe_plans
from omamods.nexus_api import NexusFile
from omamods.nexus_config import UserSettings
from omamods.nexus_workflow import (
    LocalArchiveRequest,
    install_local_archive,
    revert_mod_files,
)
from omamods.pak_games import PAK_OVERLAY_GAMES, PakGameCatalog
from omamods.red_frameworks import launch_options_hint
from omamods.ue4ss_archive import (
    is_ue4ss_archive,
    is_ue4ss_game_path,
    plan_ue4ss_bundle,
    ue4ss_binaries,
    ue4ss_proxies_on_disk,
)
from tests.fakes import FakeArchiveReader

MGS_DELTA = PAK_OVERLAY_GAMES["metalgearsoliddeltasnakeeater"]
# Shaped like BetterUncapFPS v5.7's "UE4SS_All in One Package" (mod 47, file 321).
UNCAP_FPS_MEMBERS = {
    "dwmapi.dll": b"proxy",
    "Engine.ini": b"[Core.System]",
    "BetterUncapFPS v5.7 - Changelog.txt": b"notes",
    "ue4ss/UE4SS.dll": b"ue4ss",
    "ue4ss/UE4SS-settings.ini": b"GraphicsAPI = opengl",
    "ue4ss/Mods/mods.txt": b"UncapFPS : 1",
    "ue4ss/Mods/UncapFPS/scripts/main.lua": b"-- lua",
    "ue4ss/Mods/UncapFPS/scripts/UncapFPS_config.txt": b"fps=60",
}


def targets(members: tuple[str, ...]) -> dict[str, str]:
    planned = plan_ue4ss_bundle(members, MGS_DELTA)
    return {a.member: a.target.as_posix() for a in planned}


class Ue4ssPlanTests(unittest.TestCase):
    def test_bundle_goes_beside_the_exe_and_notes_stay(self) -> None:
        planned = targets(tuple(UNCAP_FPS_MEMBERS))
        self.assertEqual(planned["dwmapi.dll"], "dwmapi.dll")
        self.assertEqual(
            planned["ue4ss/Mods/UncapFPS/scripts/main.lua"],
            "ue4ss/Mods/UncapFPS/scripts/main.lua",
        )
        self.assertEqual(planned["Engine.ini"], "Engine.ini")
        self.assertNotIn("BetterUncapFPS v5.7 - Changelog.txt", planned)

    def test_engine_ini_goes_to_the_prefix_config(self) -> None:
        planned = plan_ue4ss_bundle(tuple(UNCAP_FPS_MEMBERS), MGS_DELTA)
        config = [a for a in planned if a.user_config]
        self.assertEqual([a.target.as_posix() for a in config], ["Engine.ini"])
        self.assertTrue(config[0].user_editable)
        self.assertFalse(config[0].beside_exe)

    def test_engine_ini_stays_without_a_steam_app(self) -> None:
        scanned = replace(MGS_DELTA, steam_app_id=None)
        planned = plan_ue4ss_bundle(tuple(UNCAP_FPS_MEMBERS), scanned)
        self.assertNotIn("Engine.ini", {a.member for a in planned})

    def test_config_names_take_unreal_spelling(self) -> None:
        planned = targets(("dwmapi.dll", "ue4ss/UE4SS.dll", "ENGINE.INI"))
        self.assertEqual(planned["ENGINE.INI"], "Engine.ini")

    def test_wrapping_folder_is_dropped(self) -> None:
        planned = targets(("Pack/DWMAPI.dll", "Pack/ue4ss/UE4SS.dll"))
        self.assertEqual(set(planned.values()), {"dwmapi.dll", "ue4ss/UE4SS.dll"})

    def test_settings_files_are_user_editable(self) -> None:
        planned = plan_ue4ss_bundle(tuple(UNCAP_FPS_MEMBERS), MGS_DELTA)
        editable = {a.target.name for a in planned if a.user_editable}
        self.assertEqual(
            editable,
            {"UE4SS-settings.ini", "mods.txt", "UncapFPS_config.txt", "Engine.ini"},
        )
        self.assertTrue(all(a.beside_exe != a.user_config for a in planned))

    def test_standalone_ue4ss_mods_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "standalone UE4SS mods"):
            targets(("ue4ss/Mods/UncapFPS/scripts/main.lua",))

    def test_paks_beside_the_bundle_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "destination is unknown"):
            targets(("dwmapi.dll", "ue4ss/UE4SS.dll", "LogicMods/a.pak"))

    def test_two_ue4ss_folders_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one ue4ss/"):
            targets(("A/ue4ss/UE4SS.dll", "B/ue4ss/UE4SS.dll"))

    def test_paths_differing_only_in_case_are_refused(self) -> None:
        members = ("dwmapi.dll", "ue4ss/UE4SS.dll", "ue4ss/Mods/a.lua")
        with self.assertRaisesRegex(ValueError, "ignoring case"):
            targets((*members, "ue4ss/mods/A.lua"))

    def test_engine_dispatch_sends_bundles_to_the_ue4ss_planner(self) -> None:
        members = tuple(UNCAP_FPS_MEMBERS)
        self.assertTrue(is_ue4ss_archive(members))
        self.assertFalse(is_ue4ss_archive(("~mods/a.pak",)))
        planned = plan_game_assets(members, MGS_DELTA, None)
        self.assertTrue(all(a.beside_exe or a.user_config for a in planned))
        self.assertEqual(game_variants(members, MGS_DELTA), ())

    def test_plan_description_shows_the_exe_folder(self) -> None:
        planned = plan_ue4ss_bundle(("dwmapi.dll", "ue4ss/UE4SS.dll"), MGS_DELTA)
        file = NexusFile(321, "BetterUncapFPS.zip", "MAIN", 1)
        text = describe_plans((FilePlan(file, None, planned),), "Paks")
        self.assertIn("  Binaries/Win64/ue4ss/UE4SS.dll", text)

    def test_plan_description_says_engine_ini_is_restored(self) -> None:
        planned = plan_ue4ss_bundle(tuple(UNCAP_FPS_MEMBERS), MGS_DELTA)
        file = NexusFile(321, "BetterUncapFPS.zip", "MAIN", 1)
        text = describe_plans((FilePlan(file, None, planned),), "Paks")
        self.assertIn("Saved/Config/Engine.ini (replaces the game's", text)

    def test_owned_paths_must_be_ue4ss_files(self) -> None:
        self.assertTrue(is_ue4ss_game_path("dwmapi.dll"))
        self.assertTrue(is_ue4ss_game_path("ue4ss/Mods/mods.txt"))
        for path in ("MGSDelta-Win64-Shipping.exe", "ue4ss", "/ue4ss/x", "ue4ss/../x"):
            with self.subTest(path=path):
                self.assertFalse(is_ue4ss_game_path(path))


class MgsDeltaCatalogTests(unittest.TestCase):
    def test_mgs_delta_is_a_builtin_with_its_steam_app(self) -> None:
        game = PakGameCatalog().for_domain("metalgearsoliddeltasnakeeater")
        self.assertEqual(game.paks_subpath, Path("MGSDelta/Content/Paks"))
        self.assertEqual(game.steam_app_id, "2417610")


class Ue4ssInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        project = base / "steamapps/common/MGSDelta/MGSDelta"
        self.paks = project / "Content/Paks"
        self.paks.mkdir(parents=True)
        self.binaries = project / "Binaries/Win64"
        self.binaries.mkdir(parents=True)
        (self.binaries / "MGSDelta-Win64-Shipping.exe").write_bytes(b"game")
        local = base / "steamapps/compatdata/2417610/pfx/drive_c/users/steamuser"
        self.config = local / "AppData/Local/MGSDelta/Saved/Config/Windows"
        self.config.mkdir(parents=True)
        self.engine_ini = self.config / "Engine.ini"
        self.engine_ini.write_bytes(b"[game]")
        self.settings = UserSettings("", base / "storage", {}, ())
        self.source = base / "BetterUncapFPS.zip"
        self.source.write_bytes(b"zip")
        self.reader = FakeArchiveReader(dict(UNCAP_FPS_MEMBERS))

    def _install(self) -> int:
        request = LocalArchiveRequest(self.source, 47, 321, None)
        _, count = install_local_archive(
            MGS_DELTA, self.settings, self.paks, request, self.reader
        )
        return count

    def _revert(self) -> int:
        return revert_mod_files(MGS_DELTA, self.settings.storage_root, 47, 321)

    def test_install_writes_beside_the_exe_and_revert_prunes(self) -> None:
        self.assertEqual(self._install(), 7)
        self.assertEqual((self.binaries / "dwmapi.dll").read_bytes(), b"proxy")
        self.assertFalse((self.paks / "~mods").exists())
        self.assertEqual(self._revert(), 7)
        self.assertFalse((self.binaries / "ue4ss").exists())
        self.assertFalse((self.binaries / "dwmapi.dll").exists())
        self.assertTrue((self.binaries / "MGSDelta-Win64-Shipping.exe").is_file())

    def test_revert_removes_a_config_the_mod_rewrote(self) -> None:
        # Regression: BetterUncapFPS saves UncapFPS_config.txt from the game,
        # which would otherwise block uninstalling with "file changed".
        self._install()
        config = self.binaries / "ue4ss/Mods/UncapFPS/scripts/UncapFPS_config.txt"
        config.write_bytes(b"fps=120")
        self.assertEqual(self._revert(), 7)
        self.assertFalse(config.exists())

    def test_revert_refuses_a_changed_dll(self) -> None:
        self._install()
        (self.binaries / "ue4ss/UE4SS.dll").write_bytes(b"patched")
        with self.assertRaisesRegex(ValueError, "file changed"):
            self._revert()

    def test_runtime_log_keeps_the_ue4ss_folder(self) -> None:
        self._install()
        (self.binaries / "ue4ss/UE4SS.log").write_text("log")
        self._revert()
        self.assertTrue((self.binaries / "ue4ss/UE4SS.log").is_file())
        self.assertFalse((self.binaries / "ue4ss/Mods").exists())

    def test_existing_proxy_dll_is_never_overwritten(self) -> None:
        (self.binaries / "dwmapi.dll").write_bytes(b"theirs")
        with self.assertRaisesRegex(ValueError, "expected an unowned path"):
            self._install()

    def test_record_points_at_the_exe_folder(self) -> None:
        self._install()
        record = next((self.settings.storage_root / "state").rglob("321.json"))
        state = json.loads(record.read_text())
        self.assertEqual(state["paks"], str(self.binaries.resolve()))

    def test_engine_ini_replaces_the_games_and_revert_restores_it(self) -> None:
        self._install()
        self.assertEqual(self.engine_ini.read_bytes(), b"[Core.System]")
        self.engine_ini.write_bytes(b"[rewritten by the game]")
        self._revert()
        self.assertEqual(self.engine_ini.read_bytes(), b"[game]")
        state = self.settings.storage_root / "state"
        self.assertEqual(list(state.rglob("*.originals")), [])

    def test_engine_ini_is_created_when_the_game_has_none(self) -> None:
        self.engine_ini.unlink()
        self._install()
        self.assertTrue(self.engine_ini.is_file())
        self._revert()
        self.assertFalse(self.engine_ini.exists())

    def test_failed_bundle_puts_the_games_engine_ini_back(self) -> None:
        (self.binaries / "dwmapi.dll").write_bytes(b"theirs")
        with self.assertRaises(ValueError):
            self._install()
        self.assertEqual(self.engine_ini.read_bytes(), b"[game]")
        self.assertEqual(
            list((self.settings.storage_root / "state").rglob("*.json")), []
        )

    def test_never_launched_game_is_refused(self) -> None:
        self.engine_ini.unlink()
        self.config.rmdir()
        with self.assertRaisesRegex(ValueError, "launch .* once"):
            self._install()
        self.assertFalse((self.binaries / "dwmapi.dll").exists())

    def test_binaries_must_exist(self) -> None:
        (self.binaries / "MGSDelta-Win64-Shipping.exe").unlink()
        self.binaries.rmdir()
        with self.assertRaisesRegex(ValueError, "shipping executable"):
            ue4ss_binaries(self.paks)


class Ue4ssLaunchOptionsTests(unittest.TestCase):
    def test_proxies_count_only_with_ue4ss_present(self) -> None:
        win64 = Path("/g/Binaries/Win64")
        present = {win64 / "dwmapi.dll", win64 / "ue4ss/UE4SS.dll"}
        self.assertEqual(
            ue4ss_proxies_on_disk(win64, present.__contains__), frozenset({"dwmapi"})
        )
        only_proxy = {win64 / "dwmapi.dll"}
        self.assertEqual(
            ue4ss_proxies_on_disk(win64, only_proxy.__contains__), frozenset()
        )

    def test_advice_merges_the_dwmapi_override(self) -> None:
        current = "PROTON_ENABLE_HDR=1 %command%"
        advice = launch_options_advice(
            (current,), frozenset(), None, "2417610", frozenset({"dwmapi"})
        )
        self.assertEqual(advice.missing, ("dwmapi",))
        self.assertEqual(advice.suggested, f'WINEDLLOVERRIDES="dwmapi=n,b" {current}')
        self.assertIsNone(advice.runtime_fix)

    def test_hint_names_ue4ss(self) -> None:
        self.assertIn("UE4SS mods do nothing", launch_options_hint(("dwmapi",)))
