"""Library discovery tests with isolated, named filesystem fakes."""

from pathlib import Path
import unittest

from omamods.steam_libraries import default_steam_roots, discover_libraries
from tests.fakes import FakeFiles


class LibraryTests(unittest.TestCase):
    def test_conventional_and_xdg_roots(self) -> None:
        roots = default_steam_roots(Path("/home/test"), None)
        self.assertIn(Path("/home/test/.steam/root"), roots)
        self.assertIn(
            Path("/home/test/.var/app/com.valvesoftware.Steam/.local/share/Steam"),
            roots,
        )
        self.assertEqual(
            default_steam_roots(Path("/home/test"), "/custom")[0], Path("/custom/Steam")
        )
        self.assertEqual(default_steam_roots(Path("/home/test"), "relative"), roots)

    def test_modern_libraries_and_symlink_deduplication(self) -> None:
        root, extra, alias = Path("/steam"), Path("/games drive"), Path("/alias")
        source = (
            '"libraryfolders" { "0" { "path" "/steam" } "1" { "path" "/games drive" } }'
        )
        files = FakeFiles(
            {root / "steamapps/libraryfolders.vdf": source},
            (root, root / "steamapps", extra / "steamapps"),
            {alias: root},
        )
        scan = discover_libraries((root, alias), files)
        self.assertEqual(scan.libraries, (root, extra))
        self.assertEqual(scan.warnings, ())
        self.assertEqual(len(files.reads), 1)

    def test_legacy_library_paths(self) -> None:
        root = Path("/steam")
        source = '"libraryfolders" { "TimeNextStatsReport" "0" "1" "/extra" }'
        files = FakeFiles(
            {root / "steamapps/libraryfolders.vdf": source},
            (root, root / "steamapps", Path("/extra/steamapps")),
        )
        self.assertEqual(
            discover_libraries((root,), files).libraries, (root, Path("/extra"))
        )

    def test_missing_roots_and_missing_library_file(self) -> None:
        missing = discover_libraries((Path("/missing"),), FakeFiles())
        self.assertEqual(missing.libraries, ())
        self.assertIn("No accessible Steam libraries", missing.warnings[0])
        root = Path("/steam")
        files = FakeFiles(directories=(root, root / "steamapps"))
        self.assertEqual(discover_libraries((root,), files).libraries, (root,))

    def test_malformed_library_file_preserves_primary_library(self) -> None:
        root = Path("/steam")
        for source in (
            '"libraryfolders" {',
            '"libraryfolders" { "0" "relative" }',
            '"libraryfolders" "bad"',
        ):
            files = FakeFiles(
                {root / "steamapps/libraryfolders.vdf": source},
                (root, root / "steamapps"),
            )
            scan = discover_libraries((root,), files)
            self.assertEqual(scan.libraries, (root,))
            self.assertIn("libraryfolders.vdf", scan.warnings[0])

    def test_unmounted_library_warning(self) -> None:
        root = Path("/steam")
        source = '"libraryfolders" { "0" "/offline" }'
        files = FakeFiles(
            {root / "steamapps/libraryfolders.vdf": source}, (root, root / "steamapps")
        )
        scan = discover_libraries((root,), files)
        self.assertEqual(scan.libraries, (root,))
        self.assertIn("/offline", scan.warnings[0])

    def test_permission_failure_is_reported(self) -> None:
        root = Path("/steam")
        path = root / "steamapps/libraryfolders.vdf"
        files = FakeFiles(
            directories=(root, root / "steamapps"),
            failures={path: PermissionError(f"{path}: permission denied")},
        )
        scan = discover_libraries((root,), files)
        self.assertEqual(scan.libraries, (root,))
        self.assertIn("permission denied", scan.warnings[0])
