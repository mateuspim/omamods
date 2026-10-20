"""Exercise opening and closing per-mod Nexus browser windows."""

from pathlib import Path
import tempfile
import unittest

from omamods.browser_windows import (
    NexusWindows,
    chromium_browser,
    default_browser_entry,
    exec_program,
    nexus_window_class,
)
from tests.fakes import FakeHyprland, FakeLauncher, FakeOmarchyBrowser

SB_WINDOW = {
    "address": "0x5652e6a01af0",
    "initialClass": "brave-www.nexusmods.com__stellarblade_mods_1-Default",
}
MAIN_BROWSER = {"address": "0x1", "initialClass": "brave-origin"}


class BrowserDetectionTests(unittest.TestCase):
    def test_exec_program_reads_first_word(self) -> None:
        self.assertEqual(
            exec_program("[Desktop Entry]\nExec=/home/me/bin/brave-origin %U\n"),
            "/home/me/bin/brave-origin",
        )
        self.assertIsNone(exec_program("[Desktop Entry]\n"))

    def test_default_browser_must_be_chromium_family(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            apps = Path(temporary) / "applications"
            apps.mkdir()
            entry = apps / "brave-origin.desktop"
            entry.write_text("Exec=/home/me/.local/bin/brave-origin %U\n")
            folders = (Path(temporary),)
            found = chromium_browser(FakeHyprland([]), folders)
            self.assertEqual(found, "/home/me/.local/bin/brave-origin")
            entry.write_text("Exec=firefox %u\n")
            self.assertIsNone(chromium_browser(FakeHyprland([]), folders))

    def test_omarchy_wrapper_resolves_to_the_real_browser(self) -> None:
        # Regression: omarchy-browser.desktop runs omarchy-launch-browser, which
        # hid Brave and sent Nexus pages to a tab instead of an app window.
        with tempfile.TemporaryDirectory() as temporary:
            apps = Path(temporary) / "applications"
            apps.mkdir()
            (apps / "omarchy-browser.desktop").write_text(
                "Exec=omarchy-launch-browser %U\n"
            )
            (apps / "brave-origin.desktop").write_text("Exec=/usr/bin/brave-origin\n")
            runner = FakeOmarchyBrowser("brave-origin.desktop")
            found = chromium_browser(runner, (Path(temporary),))
            self.assertEqual(found, "/usr/bin/brave-origin")

    def test_default_entry_falls_back_to_xdg_settings(self) -> None:
        self.assertEqual(
            default_browser_entry(FakeOmarchyBrowser(None)), "omarchy-browser.desktop"
        )

    def test_window_class_does_not_match_longer_mod_ids(self) -> None:
        pattern = nexus_window_class("stellarblade", 1)
        self.assertTrue(pattern.search(SB_WINDOW["initialClass"]))
        self.assertFalse(
            pattern.search("brave-www.nexusmods.com__stellarblade_mods_12-Default")
        )


class NexusWindowTests(unittest.TestCase):
    def test_open_uses_app_window_or_falls_back(self) -> None:
        launcher = FakeLauncher()
        self.assertTrue(
            NexusWindows(FakeHyprland([]), launcher, "brave").open("https://n/1")
        )
        self.assertEqual(launcher.launched[-1], ("brave", "--app=https://n/1"))
        self.assertFalse(
            NexusWindows(FakeHyprland([]), launcher, None).open("https://n/1")
        )
        self.assertEqual(launcher.launched[-1][0], "xdg-open")

    def test_close_only_the_mod_window(self) -> None:
        hyprland = FakeHyprland([MAIN_BROWSER, SB_WINDOW])
        windows = NexusWindows(hyprland, FakeLauncher(), "brave")
        self.assertEqual(windows.close_mod("stellarblade", 1), 1)
        self.assertEqual(
            hyprland.closed(),
            ['hl.dsp.window.close({ window = "address:0x5652e6a01af0" })'],
        )

    def test_legacy_hyprland_fallback(self) -> None:
        hyprland = FakeHyprland([SB_WINDOW], dispatch_reply="error")
        NexusWindows(hyprland, FakeLauncher(), "brave").close_mod("stellarblade", 1)
        self.assertEqual(
            hyprland.commands[-1][2:], ("closewindow", "address:0x5652e6a01af0")
        )

    def test_hide_moves_only_the_mod_window_silently(self) -> None:
        hyprland = FakeHyprland([MAIN_BROWSER, SB_WINDOW])
        windows = NexusWindows(hyprland, FakeLauncher(), "brave")
        self.assertEqual(windows.hide_mod("stellarblade", 1), 1)
        self.assertEqual(
            hyprland.hidden(),
            [
                'hl.dsp.window.move({ workspace = "special:omamods", '
                'follow = false, window = "address:0x5652e6a01af0" })'
            ],
        )
        self.assertEqual(hyprland.closed(), [])

    def test_hide_legacy_hyprland_fallback(self) -> None:
        hyprland = FakeHyprland([SB_WINDOW], dispatch_reply="error")
        NexusWindows(hyprland, FakeLauncher(), "brave").hide_mod("stellarblade", 1)
        self.assertEqual(
            hyprland.commands[-1][2:],
            ("movetoworkspacesilent", "special:omamods,address:0x5652e6a01af0"),
        )

    def test_unexpected_addresses_are_never_dispatched(self) -> None:
        injected = dict(SB_WINDOW, address='0x1" }) os.exit() --')
        hyprland = FakeHyprland([injected])
        self.assertEqual(
            NexusWindows(hyprland, FakeLauncher(), "b").close_mod("stellarblade", 1), 0
        )
        self.assertEqual(hyprland.closed(), [])


if __name__ == "__main__":
    unittest.main()
