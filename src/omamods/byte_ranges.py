"""Read parts of large files, so pak indexes load without the whole pak."""

from pathlib import Path
from typing import Protocol


class ByteRanges(Protocol):
    """Random access to one file's bytes; tests pass ``BytesRanges``."""

    def size(self) -> int:
        """Count the bytes; for example, ``ranges.size()``."""
        ...

    def read(self, offset: int, length: int) -> bytes:
        """Read up to ``length`` bytes; for example, ``ranges.read(0, 16)``."""
        ...


class FileRanges:
    """Read a local file by offset; e.g. ``FileRanges(Path('Mod_P.pak'))``."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def size(self) -> int:
        """Count the bytes; for example, ``FileRanges(p).size()``."""
        return self.path.stat().st_size

    def read(self, offset: int, length: int) -> bytes:
        """Read a slice; for example, ``FileRanges(p).read(0, 16)``."""
        with self.path.open("rb") as stream:
            stream.seek(offset)
            return stream.read(length)


class BytesRanges:
    """Serve bytes already in memory; e.g. ``BytesRanges(member_bytes)``."""

    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def size(self) -> int:
        """Count the bytes; for example, ``BytesRanges(b'ab').size() == 2``."""
        return len(self.raw)

    def read(self, offset: int, length: int) -> bytes:
        """Read a slice; for example, ``BytesRanges(b'abc').read(1, 1) == b'b'``."""
        return self.raw[offset : offset + length]
