"""List the game paths a legacy Unreal .pak replaces.

UE4-era mods ship plain .pak files; UE5 IoStore mods ship a stub .pak whose
index is empty (see ``iostore_index``). Versions 3-9 keep one flat index of
entries; version 10 and later keep a separate full directory index.
"""

import struct

from omamods.byte_ranges import ByteRanges
from omamods.iostore_index import IndexCursor

PAK_MAGIC = 0x5A6F12E1
MAGIC_BYTES = struct.pack("<I", PAK_MAGIC)
FIRST_VERSION = 3
FNAME_METHOD_VERSION = 8
PATH_HASH_VERSION = 10
FOOTER_SEARCH_BYTES = 512
# After the magic: version, index offset, size, hash; then 32-byte method names.
FOOTER_TAIL = struct.Struct("<IQQ20s")
METHOD_NAME_SIZE = 32
WIDE_METHOD_SLOTS = 5
INT32 = struct.Struct("<i")
UINT32 = struct.Struct("<I")
UINT8 = struct.Struct("<B")
INDEX_LOCATION = struct.Struct("<qq20s")


def pak_footer(pak: ByteRanges) -> tuple[int, int, int, int]:
    """Read version, index offset, size, method slots; e.g. ``pak_footer(ranges)``."""
    total = pak.size()
    start = max(0, total - FOOTER_SEARCH_BYTES)
    tail = pak.read(start, total - start)
    magic_at = tail.rfind(MAGIC_BYTES)
    if magic_at < 1 or magic_at + 4 + FOOTER_TAIL.size > len(tail):
        raise ValueError(
            f"pak footer: expected magic {PAK_MAGIC:#x} near the end of {total} bytes"
        )
    if tail[magic_at - 1]:
        raise ValueError("pak index: expected it unencrypted")
    version, offset, size, _ = FOOTER_TAIL.unpack_from(tail, magic_at + 4)
    after = len(tail) - magic_at - 4 - FOOTER_TAIL.size
    if version < FIRST_VERSION or offset + size > total:
        raise ValueError(
            f"pak version={version} index={offset}+{size}: expected version "
            f">= {FIRST_VERSION} with the index inside {total} bytes"
        )
    return version, offset, size, after // METHOD_NAME_SIZE


def _skip_entry(cursor: IndexCursor, version: int, wide_method: bool) -> None:
    cursor.take(struct.Struct("<qqq"))  # Offset, size, uncompressed size.
    if version < FNAME_METHOD_VERSION:
        (method,) = cursor.take(INT32)
    else:
        (method,) = cursor.take(UINT32 if wide_method else UINT8)
    cursor.take(struct.Struct("<20s"))
    if method:
        (blocks,) = cursor.take(INT32)
        cursor.take(struct.Struct(f"<{blocks * 16}s"))
    cursor.take(struct.Struct("<BI"))  # Encrypted flag, block size.


def flat_index_paths(raw: bytes, version: int, method_slots: int) -> tuple[str, ...]:
    """Read a v3-v9 index; e.g. ``flat_index_paths(index, 8, 5)``."""
    cursor = IndexCursor(raw)
    mount = cursor.text()
    (count,) = cursor.take(INT32)
    # 8b and later widened the method index when they added a fifth slot.
    wide = version > FNAME_METHOD_VERSION or method_slots >= WIDE_METHOD_SLOTS
    paths: list[str] = []
    for _ in range(count):
        paths.append(mount + cursor.text())
        _skip_entry(cursor, version, wide)
    return tuple(sorted(paths))


def _full_directory_location(cursor: IndexCursor) -> tuple[int, int] | None:
    cursor.take(struct.Struct("<iQ"))  # Entry count, path hash seed.
    (has_hash_index,) = cursor.take(UINT32)
    if has_hash_index:
        cursor.take(INDEX_LOCATION)
    (has_full_index,) = cursor.take(UINT32)
    if not has_full_index:
        return None
    offset, size, _ = cursor.take(INDEX_LOCATION)
    return offset, size


def directory_index_paths(pak: ByteRanges, raw: bytes) -> tuple[str, ...]:
    """Read a v10+ index; e.g. ``directory_index_paths(ranges, index)``."""
    cursor = IndexCursor(raw)
    mount = cursor.text()
    location = _full_directory_location(cursor)
    if location is None:
        return ()
    offset, size = location
    folders = IndexCursor(pak.read(offset, size))
    paths: list[str] = []
    for _ in range(folders.take(INT32)[0]):
        folder = folders.text().lstrip("/")
        for _ in range(folders.take(INT32)[0]):
            paths.append(mount + folder + folders.text())
            folders.take(INT32)  # Encoded entry location.
    return tuple(sorted(paths))


def pak_asset_paths(pak: ByteRanges) -> tuple[str, ...]:
    """List what a .pak replaces; e.g. ``pak_asset_paths(FileRanges(pak))``."""
    version, offset, size, slots = pak_footer(pak)
    raw = pak.read(offset, size)
    if version >= PATH_HASH_VERSION:
        return directory_index_paths(pak, raw)
    return flat_index_paths(raw, version, slots)
