"""Check the Visual C++ runtime inside a Steam game's Proton prefix.

RED4ext 1.30 and CET 1.37 are built with Visual Studio 2022 17.10+, whose
code faults on msvcp140 older than 14.40. A prefix that only got the game's
own 2020 redistributable (14.28) makes CET fail with "Unable to load
cyber_engine_tweaks.asi, Error: 998" until vcrun2022 is installed.
"""

from collections.abc import Callable
from pathlib import Path
import struct

MIN_MSVC_RUNTIME = (14, 40)
# VS_FIXEDFILEINFO starts with this signature, little-endian, then
# dwStrucVersion, dwFileVersionMS, and dwFileVersionLS.
FIXED_FILE_INFO_HEADER = struct.pack("<II", 0xFEEF04BD, 0x00010000)
FileVersion = tuple[int, int, int, int]
BytesReader = Callable[[Path], bytes]


def file_version(blob: bytes) -> FileVersion | None:
    """Read a PE file's version; e.g. ``file_version(dll.read_bytes())``."""
    # The signature bytes also occur by chance in code (CET's .asi has one
    # before its resources), so require the 1.0 structure version too.
    start = blob.find(FIXED_FILE_INFO_HEADER)
    if start < 0 or len(blob) < start + 16:
        return None
    most, least = struct.unpack_from("<II", blob, start + 8)
    return (most >> 16, most & 0xFFFF, least >> 16, least & 0xFFFF)


def steam_prefix(game_root: Path, app_id: str) -> Path:
    """Locate a Steam game's prefix; e.g. ``steam_prefix(root, '1091500')``.

    Steam keeps compatdata/ in the same library as steamapps/common/<game>.
    """
    return game_root.parent.parent / "compatdata" / app_id / "pfx"


def msvc_runtime_version(prefix: Path, read: BytesReader) -> FileVersion | None:
    """Read the 64-bit msvcp140.dll version; e.g. ``msvc_runtime_version(pfx, Path.read_bytes)``."""
    try:
        return file_version(read(prefix / "drive_c/windows/system32/msvcp140.dll"))
    except OSError:
        return None  # No prefix yet (never launched) or no runtime at all.


def is_outdated_runtime(version: FileVersion | None) -> bool:
    """True below 14.40; e.g. ``is_outdated_runtime((14, 28, 29334, 0))``."""
    return version is not None and version[:2] < MIN_MSVC_RUNTIME


def vcrun_command(app_id: str) -> str:
    """The fix to run with the game closed; e.g. ``vcrun_command('1091500')``."""
    return f"protontricks {app_id} -q vcrun2022"
