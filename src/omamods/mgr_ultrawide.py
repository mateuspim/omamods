"""Compute the ultrawide patch for METAL GEAR RISING: REVENGEANCE (Steam).

The game renders 16:9 only: it pillarboxes every resolution and lists none
wider. Reverse engineering of the Steam build (sha256 7174741f...ad34) found
what to change; nothing usable was published. The 1920x1080 menu entry becomes
the chosen resolution, the 3D camera and the final blit use the real aspect,
and the menu UI and cutscene movies keep a centred 16:9 layout through a small
getter placed in int3 padding that returns height * 16 / 9. The gameplay HUD
still stretches; see games/metalgearrising/README.md.
"""

from dataclasses import dataclass
import math
import struct

from omamods.exe_byte_patches import BytePatch, apply_byte_patches, sha256_hex

STEAM_EXE_SHA256 = "7174741f46ab4c222304b0f1b9291a2281d53368016347e65d2ea404ff07ad34"
EXE_NAME = "METAL GEAR RISING REVENGEANCE.exe"
# Virtual address minus file offset, per section of the Steam build.
TEXT_RANGE, TEXT_DELTA = (0x401000, 0x15FD000), 0x400C00
RDATA_RANGE, RDATA_DELTA = (0x15FD000, 0x187FE00), 0x401400

SCREEN_WIDTH_GETTER = 0xF98A90
UI_WIDTH_GETTER = 0x917FA2  # 28 bytes of int3 padding before the next function
TEXT_DISTANCE = UI_WIDTH_GETTER + 24
# push ecx; push edx; eax = [screen height] * 16 / 9; pop edx; pop ecx; ret
UI_WIDTH_CODE = bytes.fromhex("5152a1e006f201c1e00431d2b909000000f7f15a59c3")
# Width calls below this address are UI layout; above it is the renderer.
UI_CODE_LIMIT = 0xD40000
TEXT_CAMERA_CALL = 0xD0D999  # menu text camera keeps the real aspect
MOVIE_WIDTH_CALL = 0xDFB11C  # default width of full-screen cutscene movies
EXPECTED_UI_CALLS = 238
TEXT_FOV_DEGREES = 54.43


@dataclass(frozen=True)
class Resolution:
    """A display size at least as wide as 16:9."""

    width: int
    height: int

    def __post_init__(self) -> None:
        if not (0 < self.height <= 16384 and 0 < self.width <= 16384):
            raise ValueError(f"resolution={self}: expected 1..16384 per side")
        if self.width * 9 < self.height * 16:
            raise ValueError(
                f"resolution={self.width}x{self.height}: expected 16:9 or wider"
            )


def parse_resolution(text: str) -> Resolution:
    """Read ``WIDTHxHEIGHT``; e.g. ``parse_resolution('3440x1440')``."""
    parts = text.lower().split("x")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"resolution={text!r}: expected WIDTHxHEIGHT, e.g. 3440x1440")
    return Resolution(int(parts[0]), int(parts[1]))


def file_offset(address: int) -> int:
    """Map a virtual address to the file; e.g. ``file_offset(0xF98A90)``."""
    for (start, end), delta in ((TEXT_RANGE, TEXT_DELTA), (RDATA_RANGE, RDATA_DELTA)):
        if start <= address < end:
            return address - delta
    raise ValueError(f"address={address:#x}: expected .text or .rdata")


def _patch(address: int, original: bytes, replacement: bytes, label: str) -> BytePatch:
    return BytePatch(file_offset(address), original, replacement, label)


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _f32(value: float) -> bytes:
    return struct.pack("<f", value)


def _call_target(image: bytes, address: int) -> int:
    offset = file_offset(address)
    return address + 5 + struct.unpack_from("<i", image, offset + 1)[0]


def _call_to(address: int, target: int) -> bytes:
    return b"\xe8" + struct.pack("<i", target - (address + 5))


def ui_width_calls(image: bytes) -> tuple[int, ...]:
    """Find UI calls to the screen width getter; e.g. ``ui_width_calls(exe)``."""
    start, limit = file_offset(TEXT_RANGE[0]), file_offset(UI_CODE_LIMIT)
    calls: list[int] = []
    offset = image.find(b"\xe8", start, limit)
    while offset != -1:
        address = offset + TEXT_DELTA
        if _call_target(image, address) == SCREEN_WIDTH_GETTER:
            calls.append(address)
        offset = image.find(b"\xe8", offset + 1, limit)
    return tuple(call for call in calls if call != TEXT_CAMERA_CALL)


def _redirect(address: int, label: str) -> BytePatch:
    original = _call_to(address, SCREEN_WIDTH_GETTER)
    return _patch(address, original, _call_to(address, UI_WIDTH_GETTER), label)


def _text_distance(resolution: Resolution) -> float:
    # Menu text sits at 0.01 units per pixel; this distance fits 16:9 height.
    half_fov = math.radians(TEXT_FOV_DEGREES) / 2
    return -resolution.height * 0.01 / (2 * math.tan(half_fov))


def _ui_getter_patch(resolution: Resolution) -> BytePatch:
    code = UI_WIDTH_CODE + b"\xcc\xcc" + _f32(_text_distance(resolution))
    return _patch(UI_WIDTH_GETTER, b"\xcc" * len(code), code, "UI width getter")


def _resolution_patches(resolution: Resolution) -> tuple[BytePatch, ...]:
    width, height = resolution.width, resolution.height
    return (
        _patch(0xA1D6B2, _u32(1920), _u32(width), "menu slot width"),
        _patch(0xA1D6B7, _u32(1080), _u32(height), "menu slot height"),
        _patch(0xA30EAB, _u32(1920), _u32(width), "render slot width"),
        _patch(0xA30EBA, _u32(1080), _u32(height), "render slot height"),
        _patch(0x16EBF20, _f32(1920.0), _f32(width), "display width"),
        _patch(0x16EBF1C, _f32(1080.0), _f32(height), "display height"),
        _patch(0x16C3078, _f32(16 / 9), _f32(width / height), "camera aspect"),
    )


def _pillarbox_patches() -> tuple[BytePatch, ...]:
    nops = b"\x90" * 12
    divide_multiply = bytes.fromhex("dc3508626401dc0dc0436c01")
    # The final blit used width = H / 9 * 16; it now multiplies by the aspect.
    return (
        _patch(0xF9B975, b"\xdd\xd8", b"\xdd\xd9", "viewport width"),
        _patch(0xF9B97D, divide_multiply, nops, "viewport 16:9 maths"),
        _patch(0xF9D537, b"\xdd\xd8", b"\xdd\xd9", "reset viewport width"),
        _patch(0xF9D543, divide_multiply, nops, "reset viewport 16:9 maths"),
        _patch(0xA3A836, _u32(0x163D30C), _u32(0x16C3078), "blit uses aspect"),
        _patch(0xA3A84B, bytes.fromhex("d80d6ccf6301"), b"\x90" * 6, "blit times 16"),
    )


def _layout_patches(image: bytes, resolution: Resolution) -> tuple[BytePatch, ...]:
    text_load = _patch(0xCAD489, _u32(0x164069C), _u32(TEXT_DISTANCE), "text depth")
    calls = ui_width_calls(image)
    redirects = tuple(_redirect(call, f"UI width call {call:#x}") for call in calls)
    movie = _redirect(MOVIE_WIDTH_CALL, "cutscene movie width")
    return (_ui_getter_patch(resolution), text_load, movie, *redirects)


def ultrawide_patches(image: bytes, resolution: Resolution) -> tuple[BytePatch, ...]:
    """List every patch for one size; e.g. ``ultrawide_patches(exe, res)``."""
    return (
        *_resolution_patches(resolution),
        *_pillarbox_patches(),
        *_layout_patches(image, resolution),
    )


def build_ultrawide_exe(image: bytes, resolution: Resolution) -> bytes:
    """Patch the untouched Steam exe; e.g. ``build_ultrawide_exe(exe, res)``."""
    found = sha256_hex(image)
    if found != STEAM_EXE_SHA256:
        raise ValueError(
            f"{EXE_NAME} sha256={found}: expected the untouched Steam build "
            f"{STEAM_EXE_SHA256}; verify the game files in Steam"
        )
    calls = ui_width_calls(image)
    if len(calls) != EXPECTED_UI_CALLS:
        raise ValueError(f"UI width calls={len(calls)}: expected {EXPECTED_UI_CALLS}")
    return apply_byte_patches(image, ultrawide_patches(image, resolution))
