"""Spot Cyberpunk frameworks on disk and the Steam launch options they need."""

from pathlib import Path
import unittest

from omamods.red_frameworks import (
    CET_MOD_ID,
    RED4EXT_MOD_ID,
    frameworks_on_disk,
    launch_options_hint,
    missing_proxy_dlls,
    native_overrides,
)
from omamods.steam_launch_options import steam_launch_options
from tests.fakes import FakeFiles

ROOT = Path("/g/Cyberpunk 2077")
STEAM = Path("/steam")
LOCALCONFIG = """
"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "Apps" {
  "1091500" { "LaunchOptions" "PROTON_ENABLE_HDR=1 %command%" }
  "42" { "LastPlayed" "1" }
} } } } }
"""


class FrameworkTests(unittest.TestCase):
    def test_markers_on_disk_report_frameworks(self) -> None:
        present = {ROOT / "red4ext/RED4ext.dll", ROOT / "red4ext/plugins/ArchiveXL"}
        found = frameworks_on_disk(ROOT, lambda path: path in present)
        self.assertEqual(found, frozenset({RED4EXT_MOD_ID, 4198}))

    def test_overrides_parse_quoted_and_split_forms(self) -> None:
        self.assertEqual(
            native_overrides('WINEDLLOVERRIDES="winmm,version=n,b" %command%'),
            frozenset({"winmm", "version"}),
        )
        self.assertEqual(
            native_overrides("WINEDLLOVERRIDES=winmm=n;version=b %command%"),
            frozenset({"winmm"}),
        )

    def test_missing_dlls_only_for_frameworks_in_use(self) -> None:
        both = frozenset({RED4EXT_MOD_ID, CET_MOD_ID})
        self.assertEqual(missing_proxy_dlls(both, ()), ("version", "winmm"))
        options = ('WINEDLLOVERRIDES="winmm=n,b" %command%',)
        self.assertEqual(missing_proxy_dlls(both, options), ("version",))
        self.assertEqual(missing_proxy_dlls(frozenset({4198}), ()), ())

    def test_hint_shows_the_line_to_add(self) -> None:
        self.assertIn(
            'WINEDLLOVERRIDES="version,winmm=n,b" before %command%',
            launch_options_hint(("version", "winmm")),
        )


class LaunchOptionsTests(unittest.TestCase):
    def test_reads_each_users_options_for_the_app(self) -> None:
        files = FakeFiles(
            {
                STEAM / "userdata/1/config/localconfig.vdf": LOCALCONFIG,
                STEAM / "userdata/2/config/localconfig.vdf": '"broken',
            }
        )
        self.assertEqual(
            steam_launch_options((STEAM,), "1091500", files),
            ("PROTON_ENABLE_HDR=1 %command%",),
        )
        self.assertEqual(steam_launch_options((STEAM,), "42", files), ())


if __name__ == "__main__":
    unittest.main()
