"""Read archives bsdtar cannot, through 7-Zip, and pick a reader per archive."""

from pathlib import Path
import shutil
import subprocess
from typing import BinaryIO

from omamods.pak_archive import ArchiveReader


def parse_7z_listing(text: str) -> tuple[str, ...]:
    """Keep file paths from ``7z l -slt``; e.g. ``parse_7z_listing('Path = a.pak\\nFolder = -\\n')``."""
    members: list[str] = []
    for block in text.split("\n\n"):
        fields = dict(
            line.split(" = ", 1) for line in block.splitlines() if " = " in line
        )
        # "-ba" drops the archive header block, so every block with a Path is a member.
        if "Path" in fields and fields.get("Folder") != "+":
            members.append(fields["Path"])
    return tuple(members)


class SevenZipArchiveReader:
    """Read RAR5 archives libarchive refuses ("Declared dictionary size is not supported")."""

    def __init__(self, executable: str = "7z") -> None:
        self.executable = executable

    def members(self, archive: Path) -> tuple[str, ...]:
        """List without unpacking; for example, ``reader.members(archive)``."""
        command = (self.executable, "l", "-ba", "-slt", "--", str(archive))
        try:
            result = subprocess.run(command, capture_output=True, text=True)
        except FileNotFoundError as error:
            raise ValueError(
                f"7z={self.executable!r}: expected 7-Zip installed (pacman -S 7zip)"
            ) from error
        if result.returncode:
            raise ValueError(f"archive={str(archive)!r}: expected 7z to read it")
        return parse_7z_listing(result.stdout)

    def copy_member(self, archive: Path, member: str, destination: BinaryIO) -> None:
        """Stream one file; for example, ``reader.copy_member(rar, name, file)``."""
        # -spd: member names such as "[4K] Hair.pak" are literal, not wildcards.
        command = (self.executable, "e", "-so", "-spd", "--", str(archive), member)
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        assert process.stdout is not None
        with process.stdout:
            shutil.copyfileobj(process.stdout, destination)
        if process.wait():
            raise ValueError(f"archive member={member!r}: expected 7z to extract it")


class FallbackArchiveReader:
    """Try readers in order and remember which one read each archive."""

    def __init__(self, readers: tuple[ArchiveReader, ...]) -> None:
        self.readers = readers
        self.chosen: dict[Path, ArchiveReader] = {}

    def members(self, archive: Path) -> tuple[str, ...]:
        """List with the first reader that can; e.g. ``reader.members(rar)``."""
        failures: list[str] = []
        for reader in self.readers:
            try:
                members = reader.members(archive)
            except ValueError as error:
                failures.append(str(error))
                continue
            self.chosen[archive] = reader
            return members
        raise ValueError(
            f"archive={str(archive)!r}: expected a readable ZIP, 7z, or RAR; {failures!r}"
        )

    def copy_member(self, archive: Path, member: str, destination: BinaryIO) -> None:
        """Extract with the reader that listed it; e.g. ``reader.copy_member(rar, m, f)``."""
        if archive not in self.chosen:
            self.members(archive)
        self.chosen[archive].copy_member(archive, member, destination)
