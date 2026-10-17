"""Write launch options into Steam's localconfig.vdf, closing Steam around it."""

from datetime import datetime
from pathlib import Path
import stat
import tempfile
import unittest

from omamods.keyvalues import parse_keyvalues
from omamods.steam_launch_options import app_launch_options
from omamods.steam_launch_writer import (
    backup_folder,
    localconfig_paths,
    save_launch_options,
    set_launch_options,
)
from omamods.steam_process import SteamProcess
from tests.fakes import FakeSleep, FakeSteamClient

LINE = 'WINEDLLOVERRIDES="winmm=n,b" %command%'
# The shape Steam writes, trimmed to two apps.
LOCALCONFIG = (
    '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n'
    '\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n'
    '\t\t\t\t\t"287700"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LastPlayed"\t\t"1792201804"\n'
    '\t\t\t\t\t\t"cloud"\n\t\t\t\t\t\t{\n\t\t\t\t\t\t\t"last_sync_state"\t\t"synchronized"\n'
    "\t\t\t\t\t\t}\n\t\t\t\t\t}\n"
    '\t\t\t\t\t"1091500"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LaunchOptions"\t\t"%command% -skipStartScreen"\n'
    "\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n"
)


def options(text: str, app_id: str) -> str | None:
    return app_launch_options(parse_keyvalues(text), app_id)


class SetLaunchOptionsTests(unittest.TestCase):
    def test_inserts_a_missing_line_steam_style(self) -> None:
        edited = set_launch_options(LOCALCONFIG, "287700", LINE)
        self.assertEqual(options(edited, "287700"), LINE)
        self.assertIn(
            '\t\t\t\t\t{\n\t\t\t\t\t\t"LaunchOptions"\t\t"WINEDLLOVERRIDES=\\"winmm=n,b\\" %command%"\n'
            '\t\t\t\t\t\t"LastPlayed"',
            edited,
        )

    def test_only_the_one_value_changes(self) -> None:
        edited = set_launch_options(LOCALCONFIG, "1091500", LINE)
        self.assertEqual(options(edited, "1091500"), LINE)
        self.assertEqual(
            edited.replace(LINE.replace('"', '\\"'), "%command% -skipStartScreen"),
            LOCALCONFIG,
        )

    def test_quotes_and_backslashes_round_trip(self) -> None:
        tricky = 'A="x\\y" %command%'
        self.assertEqual(
            options(set_launch_options(LOCALCONFIG, "287700", tricky), "287700"), tricky
        )

    def test_capital_apps_and_a_byte_order_mark_work(self) -> None:
        source = "﻿" + LOCALCONFIG.replace('"apps"', '"Apps"')
        edited = set_launch_options(source, "287700", LINE)
        self.assertTrue(edited.startswith("﻿"))
        self.assertEqual(options(edited, "287700"), LINE)

    def test_an_unlisted_app_is_refused_with_a_hint(self) -> None:
        with self.assertRaisesRegex(ValueError, "Properties in Steam"):
            set_launch_options(LOCALCONFIG, "2417610", LINE)


class SaveLaunchOptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.steam = self.base / "Steam"
        self.config = self._user("91635088", LOCALCONFIG)
        self.backups = self.base / "backups"

    def _user(self, user: str, text: str) -> Path:
        config = self.steam / "userdata" / user / "config/localconfig.vdf"
        config.parent.mkdir(parents=True)
        config.write_text(text, encoding="utf-8")
        config.chmod(0o600)
        return config

    def test_writes_keeps_mode_and_backs_up(self) -> None:
        other = self._user("2", '"UserLocalConfigStore"\n{\n}\n')
        written = save_launch_options(
            (other, self.config), "287700", LINE, self.backups
        )
        self.assertEqual(written, (self.config,))
        self.assertEqual(options(self.config.read_text(), "287700"), LINE)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        backup = self.backups / "91635088/localconfig.vdf"
        self.assertEqual(backup.read_text(), LOCALCONFIG)
        self.assertEqual(
            sorted(p.name for p in self.config.parent.iterdir()), ["localconfig.vdf"]
        )

    def test_no_user_listing_the_app_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected one listing app 2417610"):
            save_launch_options((self.config,), "2417610", LINE, self.backups)
        self.assertEqual(self.config.read_text(), LOCALCONFIG)

    def test_linked_steam_roots_list_each_config_once(self) -> None:
        link = self.base / "steam-link"
        link.symlink_to(self.steam)
        self.assertEqual(localconfig_paths((self.steam, link)), (self.config,))

    def test_backup_folders_are_timestamped(self) -> None:
        folder = backup_folder(self.base, datetime(2026, 10, 16, 23, 5, 1))
        self.assertEqual(
            folder, self.base / "backups/steam-localconfig/20261016T230501"
        )


class SteamProcessTests(unittest.TestCase):
    def test_shut_down_waits_for_steam_to_exit(self) -> None:
        client = FakeSteamClient(running=True, exits_after=3)
        steam = SteamProcess(client, client, FakeSleep())
        self.assertTrue(steam.running())
        steam.shut_down()
        self.assertFalse(steam.running())
        self.assertEqual(client.launched, [("steam", "-shutdown")])
        steam.start()
        self.assertEqual(client.launched[-1], ("steam", "-silent"))

    def test_shut_down_gives_up_with_advice(self) -> None:
        client = FakeSteamClient(running=True, exits_after=10_000)
        steam = SteamProcess(client, client, FakeSleep(), timeout=2)
        with self.assertRaisesRegex(ValueError, "tray menu"):
            steam.shut_down()


if __name__ == "__main__":
    unittest.main()
