"""App matching, incomplete installation, and malformed metadata tests."""

from dataclasses import replace
from pathlib import Path
import unittest

from omamods.manifests import validate_manifest
from omamods.steam_apps import inspect_game
from omamods.steam_libraries import LibraryScan
from tests.fakes import FakeFiles, app_text, sample_fields


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("/steam")
        self.game = validate_manifest(sample_fields())
        self.path = self.root / "steamapps/appmanifest_42.acf"
        self.scan = LibraryScan((self.root,), ())

    def test_installed_game_build_and_proton_prefix(self) -> None:
        prefix = self.root / "steamapps/compatdata/42/pfx"
        install = self.root / "steamapps/common/Demo"
        files = FakeFiles({self.path: app_text()}, (install, prefix))
        result = inspect_game(self.game, self.scan, files)
        self.assertEqual(result.status, "installed")
        self.assertEqual(result.installations[0].build_id, "12345")
        self.assertEqual(result.installations[0].proton_prefix, prefix)
        self.assertEqual(files.reads, [self.path])

    def test_missing_id_does_not_guess_or_scan_apps(self) -> None:
        files = FakeFiles()
        result = inspect_game(replace(self.game, steam_app_id=None), self.scan, files)
        self.assertEqual(result.status, "app-id-unconfigured")
        self.assertEqual(files.reads, [])

    def test_not_found_and_incomplete_discovery(self) -> None:
        result = inspect_game(self.game, self.scan, FakeFiles())
        self.assertEqual(result.status, "not-found")
        scan = LibraryScan((self.root,), ("offline library",))
        self.assertEqual(
            inspect_game(self.game, scan, FakeFiles()).status, "discovery-incomplete"
        )

    def test_stale_manifest_or_partial_download(self) -> None:
        missing_files = FakeFiles({self.path: app_text()})
        result = inspect_game(self.game, self.scan, missing_files)
        self.assertEqual(result.status, "incomplete-install")
        partial = FakeFiles(
            {self.path: app_text(flags="2")}, (self.root / "steamapps/common/Demo",)
        )
        self.assertEqual(
            inspect_game(self.game, self.scan, partial).status, "incomplete-install"
        )

    def test_native_install_without_prefix_or_build_id(self) -> None:
        source = app_text().replace('"buildid" "12345"', "")
        files = FakeFiles({self.path: source}, (self.root / "steamapps/common/Demo",))
        app = inspect_game(self.game, self.scan, files).installations[0]
        self.assertIsNone(app.proton_prefix)
        self.assertIsNone(app.build_id)

    def test_malformed_apps_return_contextual_warnings(self) -> None:
        sources = (
            app_text(app_id="43"),
            app_text(flags="bad"),
            '"AppState" {',
            app_text().replace('"12345"', '"bad"'),
        )
        for source in sources:
            result = inspect_game(self.game, self.scan, FakeFiles({self.path: source}))
            self.assertEqual(result.status, "discovery-incomplete")
            self.assertIn(str(self.path), result.warnings[0])

    def test_directory_traversal_is_rejected(self) -> None:
        for directory in (
            "..",
            ".",
            "/absolute",
            "../outside",
            "sub/directory",
            "",
            " ",
            "bad\0name",
        ):
            result = inspect_game(
                self.game,
                self.scan,
                FakeFiles({self.path: app_text(directory=directory)}),
            )
            self.assertEqual(result.status, "discovery-incomplete")
            self.assertIn("installdir=", result.warnings[0])

    def test_unreadable_manifest_does_not_hide_other_installations(self) -> None:
        other = Path("/other")
        files = FakeFiles(
            {other / "steamapps/appmanifest_42.acf": app_text()},
            (other / "steamapps/common/Demo",),
            failures={self.path: PermissionError(f"{self.path}: permission denied")},
        )
        result = inspect_game(self.game, LibraryScan((self.root, other), ()), files)
        self.assertEqual(result.status, "installed")
        self.assertEqual(len(result.warnings), 1)

    def test_multiple_installations_are_preserved(self) -> None:
        other = Path("/other")
        files = FakeFiles(
            {self.path: app_text(), other / "steamapps/appmanifest_42.acf": app_text()}
        )
        result = inspect_game(self.game, LibraryScan((self.root, other), ()), files)
        self.assertEqual(len(result.installations), 2)
