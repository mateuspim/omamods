"""Apply verified byte patches to an executable image held in memory.

Exe patchers never write blindly: each patch names the bytes it expects at its
file offset, and one mismatch refuses the whole image, so a different build or
an already patched file is never corrupted.
"""

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class BytePatch:
    """Replace ``original`` with ``replacement`` at one file offset."""

    offset: int
    original: bytes
    replacement: bytes
    label: str

    def __post_init__(self) -> None:
        if len(self.original) != len(self.replacement) or not self.original:
            raise ValueError(
                f"patch {self.label!r} at {self.offset:#x}: expected equal, "
                f"nonempty lengths, got {len(self.original)} and "
                f"{len(self.replacement)}"
            )


def sha256_hex(image: bytes) -> str:
    """Hash an image; e.g. ``sha256_hex(exe_bytes)``."""
    return hashlib.sha256(image).hexdigest()


def _check_original(image: bytes, patch: BytePatch) -> None:
    end = patch.offset + len(patch.original)
    found = image[patch.offset : end]
    if found != patch.original:
        raise ValueError(
            f"patch {patch.label!r} at {patch.offset:#x}: expected bytes "
            f"{patch.original.hex()}, found {found.hex() or 'end of file'}"
        )


def _check_no_overlap(patches: Sequence[BytePatch]) -> None:
    ordered = sorted(patches, key=lambda patch: patch.offset)
    for first, second in zip(ordered, ordered[1:]):
        if first.offset + len(first.original) > second.offset:
            raise ValueError(
                f"patches {first.label!r} and {second.label!r}: expected "
                f"separate ranges, both cover {second.offset:#x}"
            )


def apply_byte_patches(image: bytes, patches: Sequence[BytePatch]) -> bytes:
    """Return a patched copy, or raise naming the first mismatch.

    Example: ``apply_byte_patches(exe, (BytePatch(0x10, b"\\xd8", b"\\xd9", "x"),))``
    """
    _check_no_overlap(patches)
    for patch in patches:
        _check_original(image, patch)
    patched = bytearray(image)
    for patch in patches:
        patched[patch.offset : patch.offset + len(patch.replacement)] = (
            patch.replacement
        )
    return bytes(patched)
