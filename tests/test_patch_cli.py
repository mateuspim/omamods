"""`omamods patch` against a temporary Steam library."""

from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from omamods.cli import run_cli
from omamods.exe_patch_games import EXE_PATCH_GAMES, ExePatchGame, exe_patch_game
from omamods.filesystem import LocalFiles
from omamods.nexus_cli import NexusRuntime
from omamods.yaml_codec import SafeYamlDecoder
from tests.fakes import app_text

MANIFEST = (
    "id: metalgearrising\nname: Demo Rising\nstatus: discovery\n"
    "platforms: [steam]\nadapter: exe-patcher\nsteam_app_id: 235460\n"
)


def _fake_build(image: bytes, option: str) -> bytes:
    return image.upper() + option.encode()


FAKE_GAME = ExePatchGame(
    game_id="metalgearrising",
    name="Demo Rising",
    exe_name="Game.exe",
    mod_title="Ultrawide patch (built in)",
    summary="Demo patch.",
    option_help="WxH",
    after_apply="Pick 1080p.",
    build=_fake_build,
)


class PatchCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        steamapps = self.root / "steam" / "steamapps"
        (steamapps / "common" / "Demo").mkdir(parents=True)
        (steamapps / "appmanifest_235460.acf").write_text(
            app_text("235460"), encoding="utf-8"
        )
        self.exe = steamapps / "common" / "Demo" / "Game.exe"
        self.exe.write_bytes(b"original")
        games = self.root / "games" / "metalgearrising"
        games.mkdir(parents=True)
        (games / "game.yml").write_text(MANIFEST, encoding="utf-8")
        self.stdout, self.stderr = StringIO(), StringIO()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, *args: str) -> int:
        environment = {"XDG_DATA_HOME": str(self.root / "data")}
        runtime = NexusRuntime.local(self.root / "home", environment)
        argv = ("--games-dir", str(self.root / "games"), "patch", *args)
        with patch.dict(EXE_PATCH_GAMES, {"metalgearrising": FAKE_GAME}):
            return run_cli(
                argv,
                LocalFiles(),
                SafeYamlDecoder(),
                (self.root / "steam",),
                self.stdout,
                self.stderr,
                runtime,
            )

    def test_apply_status_and_revert(self) -> None:
        self.assertEqual(self._run("apply", "metalgearrising", "--resolution", "x"), 0)
        self.assertEqual(self.exe.read_bytes(), b"ORIGINALx")
        backup = self.root / "data/omamods/backups/metalgearrising/Game.exe.original"
        self.assertEqual(backup.read_bytes(), b"original")
        self.assertEqual(self._run("status", "metalgearrising"), 0)
        self.assertIn("patched (Demo Rising ultrawide x)", self.stdout.getvalue())
        self.assertEqual(self._run("revert", "metalgearrising"), 0)
        self.assertEqual(self.exe.read_bytes(), b"original")

    def test_second_apply_says_revert_first(self) -> None:
        self.assertEqual(self._run("apply", "metalgearrising", "--resolution", "x"), 0)
        self.assertEqual(self._run("apply", "metalgearrising", "--resolution", "x"), 2)
        self.assertIn("already patched; revert it first", self.stderr.getvalue())
        self.assertEqual(self.exe.read_bytes(), b"ORIGINALx")

    def test_missing_exe_is_an_error(self) -> None:
        self.exe.unlink()
        self.assertEqual(self._run("status", "metalgearrising"), 2)
        self.assertIn("expected an installed Game.exe", self.stderr.getvalue())

    def test_unknown_game_lookup(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected one of"):
            exe_patch_game("nope")
        self.assertEqual(
            FAKE_GAME.describe("3440x1440"), "Demo Rising ultrawide 3440x1440"
        )


if __name__ == "__main__":
    unittest.main()
