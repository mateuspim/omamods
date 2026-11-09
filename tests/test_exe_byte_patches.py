"""Verified byte patching refuses wrong builds and overlapping edits."""

import unittest

from omamods.exe_byte_patches import BytePatch, apply_byte_patches, sha256_hex


class BytePatchTests(unittest.TestCase):
    def test_applies_every_patch_to_a_copy(self) -> None:
        image = bytes(range(16))
        patches = (
            BytePatch(2, b"\x02\x03", b"\xaa\xbb", "first"),
            BytePatch(8, b"\x08", b"\xcc", "second"),
        )
        patched = apply_byte_patches(image, patches)
        self.assertEqual(patched[2:4], b"\xaa\xbb")
        self.assertEqual(patched[8], 0xCC)
        self.assertEqual(image, bytes(range(16)))

    def test_mismatch_refuses_the_whole_image(self) -> None:
        patches = (
            BytePatch(0, b"\x00", b"\x01", "good"),
            BytePatch(4, b"\xff", b"\x01", "wrong build"),
        )
        with self.assertRaisesRegex(ValueError, "wrong build.*0x4.*ff.*04"):
            apply_byte_patches(bytes(range(8)), patches)

    def test_patch_past_the_end_names_the_end(self) -> None:
        patch = BytePatch(10, b"\x00", b"\x01", "tail")
        with self.assertRaisesRegex(ValueError, "end of file"):
            apply_byte_patches(b"\x00" * 4, (patch,))

    def test_overlapping_patches_are_refused(self) -> None:
        patches = (
            BytePatch(0, b"\x00\x01", b"\x09\x09", "a"),
            BytePatch(1, b"\x01", b"\x09", "b"),
        )
        with self.assertRaisesRegex(ValueError, "separate ranges"):
            apply_byte_patches(bytes(range(4)), patches)

    def test_lengths_must_match(self) -> None:
        with self.assertRaisesRegex(ValueError, "equal, nonempty"):
            BytePatch(0, b"\x00", b"\x00\x01", "bad")
        with self.assertRaisesRegex(ValueError, "equal, nonempty"):
            BytePatch(0, b"", b"", "empty")

    def test_sha256_hex(self) -> None:
        self.assertEqual(
            sha256_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )


if __name__ == "__main__":
    unittest.main()
