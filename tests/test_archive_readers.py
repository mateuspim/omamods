"""Fall back to 7-Zip for archives bsdtar cannot read."""

from io import BytesIO
from pathlib import Path
import unittest

from omamods.archive_readers import FallbackArchiveReader, parse_7z_listing
from tests.fakes import FakeArchiveReader

LISTING = """Path = ~mod
Folder = +
Attributes = D

Path = ~mod/Maria_P.pak
Folder = -
Size = 10

Path = [4K] Hair.utoc
Folder = -
"""


class RefusingArchiveReader:
    """Fail like bsdtar on a RAR5 archive with a large dictionary."""

    def members(self, archive: Path) -> tuple[str, ...]:
        """Refuse; for example, ``reader.members(rar)``."""
        raise ValueError(f"archive={str(archive)!r}: expected a readable archive")

    def copy_member(self, archive: Path, member: str, destination: BytesIO) -> None:
        """Refuse; extraction must not reach this reader."""
        raise AssertionError(f"member={member!r}: expected the fallback reader")


class SevenZipListingTests(unittest.TestCase):
    def test_keeps_files_and_drops_folders(self) -> None:
        self.assertEqual(
            parse_7z_listing(LISTING), ("~mod/Maria_P.pak", "[4K] Hair.utoc")
        )

    def test_empty_listing(self) -> None:
        self.assertEqual(parse_7z_listing(""), ())


class FallbackReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.second = FakeArchiveReader({"a.pak": b"pak"})
        self.reader = FallbackArchiveReader((RefusingArchiveReader(), self.second))

    def test_lists_and_extracts_with_the_reader_that_works(self) -> None:
        archive = Path("/s/mod.rar")
        self.assertEqual(self.reader.members(archive), ("a.pak",))
        stream = BytesIO()
        self.reader.copy_member(archive, "a.pak", stream)
        self.assertEqual(stream.getvalue(), b"pak")

    def test_extract_without_listing_picks_a_reader_first(self) -> None:
        stream = BytesIO()
        self.reader.copy_member(Path("/s/other.rar"), "a.pak", stream)
        self.assertEqual(stream.getvalue(), b"pak")

    def test_reports_every_failure(self) -> None:
        reader = FallbackArchiveReader((RefusingArchiveReader(),))
        with self.assertRaisesRegex(ValueError, "expected a readable ZIP, 7z, or RAR"):
            reader.members(Path("/s/bad.rar"))


if __name__ == "__main__":
    unittest.main()
