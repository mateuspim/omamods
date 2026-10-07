"""Verify filesystem adapter behavior through a named Path substitute."""

from pathlib import Path
from typing import cast
import unittest

from omamods.filesystem import LocalFiles
from tests.fakes import FakePath


class FilesystemTests(unittest.TestCase):
    def test_read_uses_bom_compatible_encoding(self) -> None:
        path = FakePath("contents")
        self.assertEqual(LocalFiles().read_text(cast(Path, path)), "contents")
        self.assertEqual(path.encoding, "utf-8-sig")

    def test_encoding_errors_have_path_context(self) -> None:
        path = FakePath(error=UnicodeError("invalid bytes"))
        with self.assertRaisesRegex(ValueError, "expected UTF-8 text.*invalid bytes"):
            LocalFiles().read_text(cast(Path, path))

    def test_directory_glob_and_canonical_path(self) -> None:
        path = cast(Path, FakePath())
        files = LocalFiles()
        self.assertTrue(files.is_dir(path))
        self.assertEqual(
            files.glob(path, "*/game.yml"), (Path("a/game.yml"), Path("z/game.yml"))
        )
        self.assertEqual(files.resolve(path), Path("/resolved"))
