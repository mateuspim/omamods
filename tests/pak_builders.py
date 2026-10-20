"""Build tiny fake .utoc and .pak files with chosen index entries."""

import struct

from omamods.iostore_index import HEADER_LAYOUT, INDEXED_FLAG, NO_ENTRY, TOC_MAGIC
from omamods.pak_index import MAGIC_BYTES

MOUNT = "../../../Game/Content/"


def fstring(text: str) -> bytes:
    """Encode an Unreal FString; e.g. ``fstring('a') == b'\\x02\\0\\0\\0a\\0'``."""
    raw = text.encode("utf-8") + b"\0"
    return struct.pack("<i", len(raw)) + raw


class DirectoryTree:
    """Lay paths out the way a .utoc directory index links them."""

    def __init__(self) -> None:
        self.names: list[str] = []
        self.directories = [[NO_ENTRY, NO_ENTRY, NO_ENTRY, NO_ENTRY]]
        self.files: list[list[int]] = []

    def _name(self, text: str) -> int:
        if text not in self.names:
            self.names.append(text)
        return self.names.index(text)

    def _child(self, parent: int, part: str) -> int:
        number = self.directories[parent][1]
        while number != NO_ENTRY:
            if self.names[self.directories[number][0]] == part:
                return number
            number = self.directories[number][2]
        sibling = self.directories[parent][1]
        self.directories.append([self._name(part), NO_ENTRY, sibling, NO_ENTRY])
        self.directories[parent][1] = len(self.directories) - 1
        return len(self.directories) - 1

    def add(self, path: str) -> None:
        """Place one file; for example, ``tree.add('Art/Hero/Body.uasset')``."""
        *folders, name = path.split("/")
        folder = 0
        for part in folders:
            folder = self._child(folder, part)
        entry = [self._name(name), self.directories[folder][3], 0]
        self.directories[folder][3] = len(self.files)
        self.files.append(entry)

    def encode(self, mount: str) -> bytes:
        """Serialize the index; for example, ``tree.encode(MOUNT)``."""
        out = fstring(mount) + struct.pack("<I", len(self.directories))
        out += b"".join(struct.pack("<IIII", *d) for d in self.directories)
        out += struct.pack("<I", len(self.files))
        out += b"".join(struct.pack("<III", *f) for f in self.files)
        out += struct.pack("<I", len(self.names))
        return out + b"".join(fstring(name) for name in self.names)


def utoc_bytes(paths: tuple[str, ...], mount: str = MOUNT) -> bytes:
    """A v5 .utoc indexing ``paths``; e.g. ``utoc_bytes(('Art/A.uasset',))``."""
    tree = DirectoryTree()
    for path in paths:
        tree.add(path)
    index = tree.encode(mount)
    header = HEADER_LAYOUT.pack(
        TOC_MAGIC, 5, HEADER_LAYOUT.size, 0, 0, 12, 0, 32, 65536,
        len(index), 1, bytes(16), INDEXED_FLAG, 0, 0, 0, 0,
    )  # fmt: skip
    return header + index


def _footer(version: int, offset: int, size: int, slots: int) -> bytes:
    tail = struct.pack("<IQQ20s", version, offset, size, bytes(20))
    return bytes(16) + b"\0" + MAGIC_BYTES + tail + bytes(32 * slots)


def flat_pak_bytes(paths: tuple[str, ...], version: int, slots: int) -> bytes:
    """A v3-v9 .pak indexing ``paths``; e.g. ``flat_pak_bytes(p, 8, 5)``."""
    method = struct.pack("<i" if version < 8 else "<I" if slots >= 5 else "<B", 0)
    entry = struct.pack("<qqq", 0, 0, 0) + method + bytes(20) + struct.pack("<BI", 0, 0)
    index = fstring(MOUNT) + struct.pack("<i", len(paths))
    index += b"".join(fstring(path) + entry for path in paths)
    data = b"payload"
    return data + index + _footer(version, len(data), len(index), slots)


def directory_pak_bytes(paths: tuple[str, ...]) -> bytes:
    """A v11 .pak with a full directory index; e.g. ``directory_pak_bytes(p)``."""
    folders: dict[str, list[str]] = {}
    for path in paths:
        folder, _, name = path.rpartition("/")
        folders.setdefault(f"/{folder}/" if folder else "/", []).append(name)
    full = struct.pack("<i", len(folders))
    for folder, names in folders.items():
        full += fstring(folder) + struct.pack("<i", len(names))
        full += b"".join(fstring(name) + struct.pack("<i", 0) for name in names)
    data = b"payload"
    index_at = len(data) + len(full)
    index = fstring(MOUNT) + struct.pack("<iQII", len(paths), 0, 0, 1)
    index += struct.pack("<qq20s", len(data), len(full), bytes(20))
    return data + full + index + _footer(11, index_at, len(index), 5)
