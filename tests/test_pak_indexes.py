"""Read the asset paths Unreal .utoc and .pak indexes list."""

import unittest

from omamods.byte_ranges import BytesRanges
from omamods.iostore_index import (
    DirectoryIndex,
    indexed_paths,
    read_toc_header,
    toc_asset_paths,
)
from omamods.pak_index import pak_asset_paths, pak_footer
from tests.pak_builders import (
    MOUNT,
    directory_pak_bytes,
    flat_pak_bytes,
    utoc_bytes,
)

HERO = ("Art/Hero/Body/Jacket.uasset", "Art/Hero/Body/Jacket.ubulk", "Art/Hair.uasset")
EXPECTED = tuple(sorted(MOUNT + path for path in HERO))


class TocIndexTests(unittest.TestCase):
    def test_lists_every_file_under_the_mount_point(self) -> None:
        self.assertEqual(toc_asset_paths(BytesRanges(utoc_bytes(HERO))), EXPECTED)

    def test_header_rejects_other_files(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected b'-==--==--==--==-'"):
            read_toc_header(b"PK\x03\x04" + bytes(200))

    def test_unindexed_container_lists_nothing(self) -> None:
        raw = bytearray(utoc_bytes(HERO))
        raw[80] = 0  # ContainerFlags (after 56 header bytes, id, and key): unindexed.
        self.assertEqual(toc_asset_paths(BytesRanges(bytes(raw))), ())

    def test_truncated_index_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected it within"):
            toc_asset_paths(BytesRanges(utoc_bytes(HERO)[:-5]))

    def test_empty_tree_has_no_paths(self) -> None:
        self.assertEqual(indexed_paths(DirectoryIndex(MOUNT, (), (), ())), ())


class PakIndexTests(unittest.TestCase):
    def test_reads_flat_indexes_of_each_layout(self) -> None:
        for version, slots in ((3, 0), (8, 4), (8, 5), (9, 5)):
            with self.subTest(version=version, slots=slots):
                pak = BytesRanges(flat_pak_bytes(HERO, version, slots))
                self.assertEqual(pak_asset_paths(pak), EXPECTED)

    def test_reads_the_full_directory_index(self) -> None:
        pak = BytesRanges(directory_pak_bytes(HERO))
        self.assertEqual(pak_asset_paths(pak), EXPECTED)

    def test_footer_reports_version_and_slots(self) -> None:
        version, _, _, slots = pak_footer(BytesRanges(flat_pak_bytes(HERO, 8, 5)))
        self.assertEqual((version, slots), (8, 5))

    def test_non_pak_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected magic 0x5a6f12e1"):
            pak_asset_paths(BytesRanges(b"not a pak"))


if __name__ == "__main__":
    unittest.main()
