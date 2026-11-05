from pathlib import Path
import tempfile
import unittest

from omamods.loose_mod_files import asi_loose_files, red_loose_files, ue4ss_loose_files


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


class RedLooseFilesTest(unittest.TestCase):
    def test_lists_mod_folders_and_loaders_but_not_game_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            touch(root / "archive/pc/content/basegame.archive")
            touch(root / "bin/x64/Cyberpunk2077.exe")
            mod = touch(root / "archive/pc/mod/a.archive")
            plugin = touch(root / "red4ext/plugins/x/x.dll")
            loader = touch(root / "bin/x64/winmm.dll")
            found = red_loose_files(root)
        self.assertEqual(set(found), {mod, plugin, loader})


class AsiLooseFilesTest(unittest.TestCase):
    def test_lists_plugin_its_settings_and_loader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            touch(root / "mgsvtpp.exe")
            touch(root / "other.ini")
            found = {
                touch(root / "MGSVFix.asi"),
                touch(root / "MGSVFix.ini"),
                touch(root / "winmm.dll"),
                touch(root / "scripts/b.asi"),
            }
            self.assertEqual(set(asi_loose_files(root)), found)

    def test_loader_alone_is_not_a_mod(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            touch(root / "winmm.dll")
            self.assertEqual(asi_loose_files(root), ())


class Ue4ssLooseFilesTest(unittest.TestCase):
    def test_lists_bundle_and_proxy_beside_the_executable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            game = Path(raw).resolve()
            paks = game / "G/Content/Paks"
            paks.mkdir(parents=True)
            touch(game / "G/Binaries/Win64/G-Win64-Shipping.exe")
            core = touch(game / "G/Binaries/Win64/ue4ss/UE4SS.dll")
            proxy = touch(game / "G/Binaries/Win64/dwmapi.dll")
            self.assertEqual(set(ue4ss_loose_files(paks)), {core, proxy})

    def test_proxy_without_ue4ss_is_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            game = Path(raw)
            paks = game / "G/Content/Paks"
            paks.mkdir(parents=True)
            touch(game / "G/Binaries/Win64/dwmapi.dll")
            self.assertEqual(ue4ss_loose_files(paks), ())


if __name__ == "__main__":
    unittest.main()
