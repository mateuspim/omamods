"""Exercise command behavior with fake Steam installations."""

import contextlib
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from omamods.cli import _parser, main, run_cli
from omamods.yaml_codec import SafeYamlDecoder
from tests.fakes import FakeFiles, app_text


class FakeCliFiles(FakeFiles):
    """Provide a minimal catalog and an installed Steam game."""

    def __init__(self) -> None:
        source = (
            "id: demo\nname: Demo Game\nstatus: discovery\nplatforms: [steam]\n"
            "adapter: undecided\nsteam_app_id: 42\nnotes: [Verify the loader.]"
        )
        super().__init__(
            {
                Path("games/demo/game.yml"): source,
                Path("/steam/steamapps/appmanifest_42.acf"): app_text(),
            },
            (
                Path("games"),
                Path("/steam"),
                Path("/steam/steamapps"),
                Path("/steam/steamapps/common/Demo"),
            ),
        )


class CliTests(unittest.TestCase):
    def test_bare_command_opens_the_tui(self) -> None:
        self.assertEqual(_parser().parse_args([]).command, "tui")
        self.assertEqual(_parser().parse_args(["game", "list"]).command, "game")

    def setUp(self) -> None:
        self.files = FakeCliFiles()
        self.stdout, self.stderr = StringIO(), StringIO()

    def _run(self, *args: str) -> int:
        return run_cli(
            args,
            self.files,
            SafeYamlDecoder(),
            (Path("/steam"),),
            self.stdout,
            self.stderr,
        )

    def test_list_catalog_games(self) -> None:
        self.assertEqual(self._run("game", "list"), 0)
        self.assertIn("demo\tDemo Game\tundecided\tinstalled", self.stdout.getvalue())
        self.assertEqual(self.stderr.getvalue(), "")

    def test_inspect_installed_game(self) -> None:
        self.assertEqual(self._run("inspect", "demo"), 0)
        output = self.stdout.getvalue()
        self.assertIn("Steam build ID: 12345", output)
        self.assertIn("Game directory: /steam/steamapps/common/Demo", output)
        self.assertIn("Steam marks fully installed: yes", output)
        self.assertIn("Proton prefix: not found", output)
        self.assertIn("Note: Verify the loader.", output)
        self.assertIn("Read-only discovery", output)

    def test_placeholder_is_not_reported_as_missing_game(self) -> None:
        path = Path("games/demo/game.yml")
        self.files.contents[path] = self.files.contents[path].replace(
            "steam_app_id: 42", ""
        )
        self.assertEqual(self._run("inspect", "demo"), 0)
        self.assertIn("app-id-unconfigured", self.stdout.getvalue())
        self.assertIn("Set a verified steam_app_id", self.stdout.getvalue())

    def test_unknown_game_and_missing_catalog(self) -> None:
        self.assertEqual(self._run("inspect", "unknown"), 2)
        self.assertIn("game='unknown': expected", self.stderr.getvalue())
        self.assertEqual(self._run("--games-dir", "/absent", "game", "list"), 2)
        self.assertIn("/absent", self.stderr.getvalue())

    def test_explicit_steam_root(self) -> None:
        self.assertEqual(self._run("--steam-root", "/steam", "inspect", "demo"), 0)
        self.assertEqual(self._run("--steam-root", "/absent", "inspect", "demo"), 2)
        self.assertIn(
            "expected a directory containing steamapps", self.stderr.getvalue()
        )

    def test_warnings_have_nonzero_status(self) -> None:
        self.files.contents[Path("/steam/steamapps/libraryfolders.vdf")] = '"broken" {'
        self.assertEqual(self._run("game", "list"), 1)
        self.assertIn("Warning:", self.stderr.getvalue())
        self.assertIn("installed", self.stdout.getvalue())

    def test_no_steam_reports_incomplete_discovery(self) -> None:
        self.files.directories = {Path("games")}
        self.assertEqual(self._run("inspect", "demo"), 1)
        self.assertIn("discovery-incomplete", self.stdout.getvalue())
        self.assertIn("No accessible Steam libraries found", self.stderr.getvalue())

    def test_incomplete_installation_report(self) -> None:
        self.files.directories.remove(Path("/steam/steamapps/common/Demo"))
        self.assertEqual(self._run("inspect", "demo"), 0)
        self.assertIn("incomplete-install", self.stdout.getvalue())
        self.assertIn("Game directory present: no", self.stdout.getvalue())

    def test_main_composition(self) -> None:
        args = ["omamods", "--steam-root", "/steam", "game", "list"]
        with (
            patch.object(sys, "argv", args),
            patch("omamods.cli.LocalFiles", FakeCliFiles),
        ):
            with (
                contextlib.redirect_stdout(self.stdout),
                contextlib.redirect_stderr(self.stderr),
            ):
                self.assertEqual(main(), 0)
        self.assertIn("Demo Game", self.stdout.getvalue())

    def test_help_and_invalid_command(self) -> None:
        with (
            contextlib.redirect_stdout(self.stdout),
            self.assertRaises(SystemExit) as result,
        ):
            self._run("--help")
        self.assertEqual(result.exception.code, 0)
        with (
            contextlib.redirect_stderr(self.stderr),
            self.assertRaises(SystemExit) as result,
        ):
            self._run("profile", "apply", "demo/default")
        self.assertEqual(result.exception.code, 2)
