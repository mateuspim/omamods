"""Pack loose natives/ files into an RE Engine patch pak, as Fluffy Mod Manager does.

Format (KPKA 4.0, checked against RESIDENT EVIL 7's re_chunk_000.pak): a
16-byte header, then one 48-byte entry per file, then the file contents. The
engine finds files by the Murmur3 hashes of their lowercase and uppercase
UTF-16LE paths, so the pak stores no names.
"""

from collections.abc import Callable
import struct
from typing import BinaryIO

PAK_MAGIC = b"KPKA"
PAK_MAJOR_VERSION = 4
HEADER = struct.Struct("<4sBBHII")
ENTRY = struct.Struct("<IIQQQQQ")
PATH_HASH_SEED = 0xFFFFFFFF
UNCOMPRESSED = 0
# Copies one archive member into the stream at its current position.
MemberCopier = Callable[[BinaryIO], None]


def _rotate_left(value: int, bits: int) -> int:
    return ((value << bits) | (value >> (32 - bits))) & 0xFFFFFFFF


def _scrambled(block: int) -> int:
    block = (block * 0xCC9E2D51) & 0xFFFFFFFF
    return (_rotate_left(block, 15) * 0x1B873593) & 0xFFFFFFFF


def _finalised(value: int, length: int) -> int:
    value ^= length
    value ^= value >> 16
    value = (value * 0x85EBCA6B) & 0xFFFFFFFF
    value ^= value >> 13
    value = (value * 0xC2B2AE35) & 0xFFFFFFFF
    return value ^ (value >> 16)


def murmur3_32(data: bytes, seed: int) -> int:
    """Hash like the engine; e.g. ``murmur3_32(b'', 0) == 0``."""
    value = seed
    whole = len(data) // 4 * 4
    for (block,) in struct.iter_unpack("<I", data[:whole]):
        value = _rotate_left(value ^ _scrambled(block), 13)
        value = (value * 5 + 0xE6546B64) & 0xFFFFFFFF
    tail = int.from_bytes(data[whole:], "little")
    if len(data) > whole:
        value ^= _scrambled(tail)
    return _finalised(value, len(data))


def path_hashes(path: str) -> tuple[int, int]:
    """Name a file the engine's way; e.g. ``path_hashes('natives/stm/a.tex.35')``."""
    lower = murmur3_32(path.lower().encode("utf-16le"), PATH_HASH_SEED)
    upper = murmur3_32(path.upper().encode("utf-16le"), PATH_HASH_SEED)
    return lower, upper


def _entry(path: str, offset: int, size: int) -> bytes:
    lower, upper = path_hashes(path)
    # The checksum field is left 0, as REtool-built mod paks do.
    return ENTRY.pack(lower, upper, offset, size, size, UNCOMPRESSED, 0)


def write_re_pak(stream: BinaryIO, files: tuple[tuple[str, MemberCopier], ...]) -> None:
    """Write files uncompressed; e.g. ``write_re_pak(out, (('natives/stm/a', copy),))``."""
    start = stream.tell()
    stream.write(HEADER.pack(PAK_MAGIC, PAK_MAJOR_VERSION, 0, 0, len(files), 0))
    stream.write(b"\0" * ENTRY.size * len(files))
    entries: list[bytes] = []
    for path, copy in files:
        offset = stream.tell() - start
        copy(stream)
        entries.append(_entry(path, offset, stream.tell() - start - offset))
    end = stream.tell()
    stream.seek(start + HEADER.size)
    stream.write(b"".join(entries))
    stream.seek(end)


def pak_major_version(header: bytes) -> int | None:
    """Read a pak's format version; e.g. ``pak_major_version(stream.read(16))``."""
    if len(header) < HEADER.size or header[:4] != PAK_MAGIC:
        return None
    return header[4]
