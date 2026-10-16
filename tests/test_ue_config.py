"""Find an Unreal game's config folder in its Proton prefix."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from omamods.original_files import put_back_original, set_aside_original
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.ue_config import (
    canonical_config_name,
    config_record,
    is_ue_config_path,
    ue_config_folder,
)

MGS_DELTA = PAK_OVERLAY_GAMES["metalgearsoliddeltasnakeeater"]
LOCAL = "steamapps/compatdata/2417610/pfx/drive_c/users/steamuser/AppData/Local"


class UeConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.paks = self.base / "steamapps/common/MGSDelta/MGSDelta/Content/Paks"
        self.config = self.base / LOCAL / "MGSDelta/Saved/Config"

    def test_unreal_5_folder(self) -> None:
        (self.config / "Windows").mkdir(parents=True)
        self.assertEqual(
            ue_config_folder(self.paks, MGS_DELTA), self.config / "Windows"
        )

    def test_unreal_4_folder(self) -> None:
        (self.config / "WindowsNoEditor").mkdir(parents=True)
        found = ue_config_folder(self.paks, MGS_DELTA)
        self.assertEqual(found, self.config / "WindowsNoEditor")

    def test_game_without_steam_app_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected a Steam game"):
            ue_config_folder(self.paks, replace(MGS_DELTA, steam_app_id=None))

    def test_names_and_records(self) -> None:
        self.assertEqual(
            canonical_config_name("gameusersettings.INI"), "GameUserSettings.ini"
        )
        self.assertTrue(is_ue_config_path("Engine.ini"))
        for path in ("engine.ini", "Saved/Engine.ini", "Other.ini"):
            with self.subTest(path=path):
                self.assertFalse(is_ue_config_path(path))
        self.assertEqual(config_record(Path("s/321.json")), Path("s/321.config.json"))


class OriginalFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.target = base / "Engine.ini"
        self.folder = base / "321.config.originals"
        self.saved = self.folder / "Engine.ini"

    def test_set_aside_and_put_back(self) -> None:
        self.target.write_text("game")
        self.assertEqual(set_aside_original(self.target, self.saved), self.saved)
        self.assertFalse(self.target.exists())
        self.target.write_text("mod")
        put_back_original(self.saved, self.target, self.folder)
        self.assertEqual(self.target.read_text(), "game")
        self.assertFalse(self.folder.exists())

    def test_nothing_to_set_aside(self) -> None:
        self.assertIsNone(set_aside_original(self.target, self.saved))

    def test_stale_copy_is_never_overwritten(self) -> None:
        self.target.write_text("game")
        self.folder.mkdir()
        self.saved.write_text("older")
        with self.assertRaisesRegex(ValueError, "expected none"):
            set_aside_original(self.target, self.saved)
        self.assertEqual(self.target.read_text(), "game")
