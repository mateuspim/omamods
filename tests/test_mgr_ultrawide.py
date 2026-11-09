"""The MGR ultrawide patch list, built against a synthetic exe image."""

import struct
import unittest

from omamods.exe_byte_patches import apply_byte_patches
from omamods.mgr_ultrawide import (
    MOVIE_WIDTH_CALL,
    SCREEN_WIDTH_GETTER,
    TEXT_CAMERA_CALL,
    UI_CODE_LIMIT,
    UI_WIDTH_GETTER,
    Resolution,
    build_ultrawide_exe,
    file_offset,
    parse_resolution,
    ui_width_calls,
    ultrawide_patches,
)

UI_CALLS = (0x479932, 0xCACE3B)
RENDER_CALL = UI_CODE_LIMIT + 0x100
IMAGE_SIZE = file_offset(0x16EBF30)


def _call_bytes(address: int, target: int) -> bytes:
    return b"\xe8" + struct.pack("<i", target - (address + 5))


def _synthetic_exe() -> bytes:
    """Zeros plus width calls and every byte the patch expects to find."""
    image = bytearray(IMAGE_SIZE)
    for call in (*UI_CALLS, TEXT_CAMERA_CALL, RENDER_CALL):
        image[file_offset(call) : file_offset(call) + 5] = _call_bytes(
            call, SCREEN_WIDTH_GETTER
        )
    for patch in ultrawide_patches(bytes(image), Resolution(3440, 1440)):
        image[patch.offset : patch.offset + len(patch.original)] = patch.original
    return bytes(image)


def _u32(image: bytes, address: int) -> int:
    return struct.unpack_from("<I", image, file_offset(address))[0]


def _f32(image: bytes, address: int) -> float:
    return struct.unpack_from("<f", image, file_offset(address))[0]


def _target(image: bytes, call: int) -> int:
    return call + 5 + struct.unpack_from("<i", image, file_offset(call) + 1)[0]


class ResolutionTests(unittest.TestCase):
    def test_parse_resolution(self) -> None:
        self.assertEqual(parse_resolution("3440X1440"), Resolution(3440, 1440))

    def test_rejects_malformed_and_narrow_sizes(self) -> None:
        for text in ("3440", "3440x", "ax1440", "3440x1440x2", "-1x5"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_resolution(text)
        with self.assertRaisesRegex(ValueError, "16:9 or wider"):
            parse_resolution("1600x1200")
        with self.assertRaisesRegex(ValueError, "1..16384"):
            Resolution(0, 1080)

    def test_file_offset_by_section(self) -> None:
        self.assertEqual(file_offset(0xF98A90), 0xF98A90 - 0x400C00)
        self.assertEqual(file_offset(0x16C3078), 0x16C3078 - 0x401400)
        with self.assertRaisesRegex(ValueError, "expected .text or .rdata"):
            file_offset(0x1F206DC)


class PatchListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original = _synthetic_exe()
        patches = ultrawide_patches(cls.original, Resolution(3440, 1440))
        cls.patched = apply_byte_patches(cls.original, patches)

    def test_only_ui_width_calls_are_found(self) -> None:
        self.assertEqual(ui_width_calls(self.original), UI_CALLS)

    def test_ui_and_movie_calls_use_the_16_9_getter(self) -> None:
        for call in (*UI_CALLS, MOVIE_WIDTH_CALL):
            self.assertEqual(_target(self.patched, call), UI_WIDTH_GETTER)
        for call in (TEXT_CAMERA_CALL, RENDER_CALL):
            self.assertEqual(_target(self.patched, call), SCREEN_WIDTH_GETTER)

    def test_menu_entry_and_aspect_take_the_resolution(self) -> None:
        self.assertEqual(_u32(self.patched, 0xA1D6B2), 3440)
        self.assertEqual(_u32(self.patched, 0xA30EBA), 1440)
        self.assertEqual(_f32(self.patched, 0x16EBF20), 3440.0)
        self.assertAlmostEqual(_f32(self.patched, 0x16C3078), 3440 / 1440, places=5)

    def test_text_depth_fits_the_height(self) -> None:
        self.assertAlmostEqual(_f32(self.patched, UI_WIDTH_GETTER + 24), -14.0, 2)
        self.assertEqual(_u32(self.patched, 0xCAD489), UI_WIDTH_GETTER + 24)

    def test_pillarbox_and_blit_use_the_full_width(self) -> None:
        start = file_offset(0xF9B975)
        self.assertEqual(self.patched[start : start + 2], b"\xdd\xd9")
        self.assertEqual(_u32(self.patched, 0xA3A836), 0x16C3078)

    def test_patching_twice_is_refused(self) -> None:
        patches = ultrawide_patches(self.patched, Resolution(3440, 1440))
        with self.assertRaisesRegex(ValueError, "expected bytes"):
            apply_byte_patches(self.patched, patches)

    def test_build_refuses_other_builds(self) -> None:
        with self.assertRaisesRegex(ValueError, "untouched Steam build"):
            build_ultrawide_exe(self.original, Resolution(3440, 1440))


if __name__ == "__main__":
    unittest.main()
