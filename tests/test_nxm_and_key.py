"""Exercise nxm link registration and handling, and saving the API key."""

from http.client import InvalidURL
import json
from pathlib import Path
import tempfile
import unittest

from omamods.cli import default_games_dir
from omamods.host_cli import omamods_executable
from omamods.nexus_api import NexusApi
from omamods.nexus_config import parse_user_config, save_api_key, with_api_key
from omamods.pak_games import PakGameCatalog
from omamods.nxm_handler import (
    DESKTOP_ENTRY_NAME,
    desktop_entry,
    handle_nxm_click,
    register_nxm_handler,
)
from tests.fakes import FakeCommandRunner, FakeConfigFiles, FakeNexusSite

LINK = "nxm://stellarblade/mods/1/files/7?key=a&expires=9"


class NxmHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_desktop_entry_quotes_and_rejects_unsafe_paths(self) -> None:
        entry = desktop_entry(Path("/home/me/my venv/bin/omamods"))
        self.assertIn('Exec="/home/me/my venv/bin/omamods" nxm handle %u', entry)
        plain = desktop_entry(Path("/home/me/.venv/bin/omamods"))
        self.assertIn("Exec=/home/me/.venv/bin/omamods nxm handle %u", plain)
        with self.assertRaisesRegex(ValueError, "without quotes"):
            desktop_entry(Path("/home/$USER/omamods"))
        with self.assertRaisesRegex(ValueError, "absolute path"):
            desktop_entry(Path("omamods"))

    def test_register_reports_previous_handler(self) -> None:
        runner = FakeCommandRunner(output="vortex.desktop")
        result = register_nxm_handler(Path("/bin/omamods"), self.root, runner)
        self.assertEqual(result.previous_handler, "vortex.desktop")
        self.assertTrue((self.root / DESKTOP_ENTRY_NAME).is_file())
        self.assertEqual(
            runner.commands[-2][:3], ("xdg-mime", "default", DESKTOP_ENTRY_NAME)
        )
        self.assertEqual(runner.commands[-1][0], "update-desktop-database")

    def test_register_fails_when_xdg_mime_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "xdg-mime exit=1"):
            register_nxm_handler(Path("/bin/omamods"), self.root, FakeCommandRunner(1))

    def test_click_stages_logs_and_notifies(self) -> None:
        runner = FakeCommandRunner()
        api = NexusApi(FakeNexusSite(premium=False), "k")
        self.assertEqual(
            handle_nxm_click(LINK, api, self.root, runner, PakGameCatalog()), 0
        )
        event = json.loads((self.root / "logs/nxm.jsonl").read_text())
        self.assertEqual((event["status"], event["game"]), ("staged", "stellar-blade"))
        self.assertNotIn("key=a", json.dumps(event))
        self.assertEqual(runner.commands[-1][0], "notify-send")

    def test_old_version_click_gets_warning_title(self) -> None:
        site = FakeNexusSite(premium=False)
        site.old_version_ids = {7}
        runner = FakeCommandRunner()
        handle_nxm_click(LINK, NexusApi(site, "k"), self.root, runner, PakGameCatalog())
        _, title, body = runner.commands[-1]
        self.assertIn("OLD", title)
        self.assertEqual(body, "Black 1.0 (OLD_VERSION)")

    def test_bad_click_is_logged_as_failure(self) -> None:
        api = NexusApi(FakeNexusSite(), "k")
        code = handle_nxm_click(
            "nxm://bad", api, self.root, FakeCommandRunner(), PakGameCatalog()
        )
        self.assertEqual(code, 1)
        self.assertIn('"failed"', (self.root / "logs/nxm.jsonl").read_text())

    def test_unexpected_errors_are_logged_not_crashing(self) -> None:
        # Regression: http.client.InvalidURL escaped the handler, leaving no log entry.
        site = FakeNexusSite(premium=False)
        site.broken_download_error = InvalidURL("URL can't contain control characters")
        code = handle_nxm_click(
            LINK, NexusApi(site, "k"), self.root, FakeCommandRunner(), PakGameCatalog()
        )
        self.assertEqual(code, 1)
        self.assertIn("InvalidURL", (self.root / "logs/nxm.jsonl").read_text())

    def test_executable_prefers_invoked_script(self) -> None:
        script = self.root / "omamods"
        script.write_text("")
        self.assertEqual(omamods_executable(str(script)), script)

    def test_games_dir_falls_back_to_checkout(self) -> None:
        self.assertEqual(default_games_dir(self.root).name, "games")
        self.assertTrue((default_games_dir(self.root) / "stellar-blade").is_dir())
        (self.root / "games").mkdir()
        self.assertEqual(default_games_dir(self.root), Path("games"))


class ApiKeyTests(unittest.TestCase):
    def test_replaces_empty_key_line(self) -> None:
        updated = with_api_key('[nexus]\napi_key = ""\n', "abc123")
        self.assertEqual(parse_user_config(updated, Path("/d"), None).api_key, "abc123")

    def test_adds_missing_section(self) -> None:
        updated = with_api_key("[storage]\nroot = '/d'\n", "abc")
        self.assertEqual(parse_user_config(updated, Path("/d"), None).api_key, "abc")

    def test_rejects_keys_that_break_toml(self) -> None:
        with self.assertRaisesRegex(ValueError, "without spaces or quotes"):
            with_api_key("", 'a"b')

    def test_save_creates_private_config(self) -> None:
        files = FakeConfigFiles()
        save_api_key(Path("/c/config.toml"), Path("/data"), "abc", files)
        text = files.contents[Path("/c/config.toml")]
        self.assertEqual(parse_user_config(text, Path("/d"), None).api_key, "abc")


if __name__ == "__main__":
    unittest.main()
