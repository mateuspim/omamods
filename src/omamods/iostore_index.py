"""List the game paths an IoStore container (.utoc) replaces.

Unreal 5 mods ship ``Name_P.utoc``/``.ucas`` with a stub ``.pak``. The .utoc's
directory index names every packaged file relative to its mount point, which
is how two mods that replace the same asset can be told apart from two mods
that only share a file name.
"""

from dataclasses import dataclass
import struct

from omamods.byte_ranges import ByteRanges

TOC_MAGIC = b"-==--==--==--==-"
HEADER_LAYOUT = struct.Struct("<16sB3xIIIIIIIII8x16sB3xIQII40x")
CHUNK_ID_SIZE = 12
OFFSET_LENGTH_SIZE = 10
COMPRESSION_BLOCK_SIZE = 12
HASH_SEED_SIZE = 4
# EIoContainerFlags and EIoStoreTocVersion values from the engine source.
ENCRYPTED_FLAG = 0x2
SIGNED_FLAG = 0x4
INDEXED_FLAG = 0x8
PERFECT_HASH_VERSION = 4
OVERFLOW_HASH_VERSION = 5
NO_ENTRY = 0xFFFFFFFF


@dataclass(frozen=True)
class TocHeader:
    """The .utoc fields needed to find its directory index."""

    version: int
    header_size: int
    entry_count: int
    block_count: int
    block_entry_size: int
    method_count: int
    method_length: int
    index_size: int
    flags: int
    seed_count: int
    overflow_count: int


def read_toc_header(toc: bytes) -> TocHeader:
    """Read a .utoc header; e.g. ``read_toc_header(path.read_bytes()).version``."""
    if len(toc) < HEADER_LAYOUT.size or not toc.startswith(TOC_MAGIC):
        raise ValueError(
            f"utoc header={toc[:16]!r}: expected {TOC_MAGIC!r} and "
            f"{HEADER_LAYOUT.size} header bytes"
        )
    fields = HEADER_LAYOUT.unpack_from(toc)
    # fields: magic, version, size, entries, blocks, block size, methods,
    # method length, block size, index size, partitions, key, flags,
    # seeds, partition size, overflow.
    return TocHeader(
        fields[1], fields[2], fields[3], fields[4], fields[5], fields[6],
        fields[7], fields[9], fields[12], fields[13], fields[15],
    )  # fmt: skip


def index_offset(header: TocHeader) -> int:
    """Where the directory index starts; e.g. ``index_offset(header)``."""
    offset = header.header_size
    offset += header.entry_count * (CHUNK_ID_SIZE + OFFSET_LENGTH_SIZE)
    if header.version >= PERFECT_HASH_VERSION:
        offset += header.seed_count * HASH_SEED_SIZE
    if header.version >= OVERFLOW_HASH_VERSION:
        offset += header.overflow_count * HASH_SEED_SIZE
    offset += header.block_count * header.block_entry_size
    offset += header.method_count * header.method_length
    if header.flags & SIGNED_FLAG:
        raise ValueError(
            f"utoc flags={header.flags:#x}: expected an unsigned container; "
            "signed indexes are not read yet"
        )
    return offset


class IndexCursor:
    """Read little-endian values from a directory index; e.g. ``IndexCursor(b)``."""

    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.offset = 0

    def take(self, layout: struct.Struct) -> tuple[int, ...]:
        """Read one record; for example, ``cursor.take(struct.Struct('<I'))``."""
        if self.offset + layout.size > len(self.raw):
            raise ValueError(
                f"utoc index offset={self.offset}: expected {layout.size} more "
                f"bytes of {len(self.raw)}"
            )
        values = layout.unpack_from(self.raw, self.offset)
        self.offset += layout.size
        return values

    def text(self) -> str:
        """Read an FString; for example, ``cursor.text()``."""
        (length,) = self.take(struct.Struct("<i"))
        wide = length < 0
        size = -length * 2 if wide else length
        end = self.offset + size
        if end > len(self.raw):
            raise ValueError(f"utoc string length={length}: runs past the index")
        chunk, self.offset = self.raw[self.offset : end], end
        return chunk.decode("utf-16-le" if wide else "utf-8").rstrip("\0")

    def records(self, layout: struct.Struct) -> tuple[tuple[int, ...], ...]:
        """Read a counted array; for example, ``cursor.records(entry)``."""
        (count,) = self.take(struct.Struct("<I"))
        return tuple(self.take(layout) for _ in range(count))


DIRECTORY_ENTRY = struct.Struct("<IIII")
FILE_ENTRY = struct.Struct("<III")


@dataclass(frozen=True)
class DirectoryIndex:
    """A .utoc's directory tree, names still as string-table numbers."""

    mount_point: str
    directories: tuple[tuple[int, ...], ...]
    files: tuple[tuple[int, ...], ...]
    names: tuple[str, ...]

    def name(self, number: int) -> str:
        """Look a name up; for example, ``index.name(3)``."""
        if number == NO_ENTRY:
            return ""
        if number >= len(self.names):
            raise ValueError(
                f"utoc name={number}: expected fewer than {len(self.names)}"
            )
        return self.names[number]


def read_directory_index(raw: bytes) -> DirectoryIndex:
    """Decode a directory index; e.g. ``read_directory_index(index_bytes)``."""
    cursor = IndexCursor(raw)
    mount = cursor.text()
    directories = cursor.records(DIRECTORY_ENTRY)
    files = cursor.records(FILE_ENTRY)
    (count,) = cursor.take(struct.Struct("<I"))
    names = tuple(cursor.text() for _ in range(count))
    return DirectoryIndex(mount, directories, files, names)


def _file_names(index: DirectoryIndex, first: int, folder: str) -> list[str]:
    paths: list[str] = []
    while first != NO_ENTRY:
        name, first, _ = index.files[first]
        paths.append(folder + index.name(name))
    return paths


def indexed_paths(index: DirectoryIndex) -> tuple[str, ...]:
    """Every file path under the mount point; e.g. ``indexed_paths(index)``."""
    paths: list[str] = []
    pending = [(0, index.mount_point)] if index.directories else []
    while pending:
        number, folder = pending.pop()
        name, child, sibling, first_file = index.directories[number]
        here = folder + index.name(name) + "/" if number else folder
        paths.extend(_file_names(index, first_file, here))
        for nxt, base in ((child, here), (sibling, folder)):
            if nxt != NO_ENTRY:
                pending.append((nxt, base))
    return tuple(sorted(paths))


def toc_asset_paths(toc: ByteRanges) -> tuple[str, ...]:
    """List what a container replaces; e.g. ``toc_asset_paths(FileRanges(utoc))``."""
    header = read_toc_header(toc.read(0, HEADER_LAYOUT.size))
    if not header.flags & INDEXED_FLAG or header.index_size == 0:
        return ()
    if header.flags & ENCRYPTED_FLAG:
        raise ValueError(
            f"utoc flags={header.flags:#x}: expected an unencrypted directory index"
        )
    raw = toc.read(index_offset(header), header.index_size)
    if len(raw) != header.index_size:
        raise ValueError(
            f"utoc index size={header.index_size}: expected it within "
            f"{toc.size()} bytes"
        )
    return indexed_paths(read_directory_index(raw))
