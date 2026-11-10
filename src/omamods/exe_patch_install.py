"""Replace a game executable with a patched build and put the original back.

The original is copied into host storage before the exe is replaced, and a
JSON record keeps both hashes. Revert restores only while the exe still has
the patched hash; a Steam update or file verification that already brought
the original back just clears the record. See docs/adr/0008.
"""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil

from omamods.exe_byte_patches import sha256_hex

RECORD_NAME = "exe-patch.json"


@dataclass(frozen=True)
class ExePatchTarget:
    """Where one game's exe, patch record, and original copy live."""

    exe: Path
    record: Path
    backup: Path

    @classmethod
    def for_game(cls, storage_root: Path, game_id: str, exe: Path) -> "ExePatchTarget":
        """Name storage paths; e.g. ``ExePatchTarget.for_game(root, 'mgr', exe)``."""
        record = storage_root / "state" / game_id / RECORD_NAME
        backup = storage_root / "backups" / game_id / f"{exe.name}.original"
        return cls(exe, record, backup)


@dataclass(frozen=True)
class ExePatchRecord:
    """What was patched, so revert can tell the patch from other changes."""

    exe: str
    original_sha256: str
    patched_sha256: str
    description: str


def load_patch_record(target: ExePatchTarget) -> ExePatchRecord | None:
    """Read the record, or None; e.g. ``load_patch_record(target)``."""
    if not target.record.is_file():
        return None
    fields = json.loads(target.record.read_text(encoding="utf-8"))
    if not isinstance(fields, dict) or set(fields) != set(
        ExePatchRecord.__annotations__
    ):
        raise ValueError(
            f"record={str(target.record)!r}: expected keys "
            f"{sorted(ExePatchRecord.__annotations__)!r}"
        )
    return ExePatchRecord(**{key: str(value) for key, value in fields.items()})


def _write_atomically(path: Path, content: bytes) -> None:
    temporary = path.with_name(path.name + ".omamods-tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _save_record(target: ExePatchTarget, record: ExePatchRecord) -> None:
    target.record.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(asdict(record), indent=2) + "\n"
    _write_atomically(target.record, text.encode("utf-8"))


def _keep_original(target: ExePatchTarget) -> None:
    if target.backup.exists():
        raise ValueError(
            f"backup={str(target.backup)!r}: expected none; an earlier patch "
            "was not reverted cleanly"
        )
    target.backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target.exe, target.backup)


def ensure_unpatched(target: ExePatchTarget) -> None:
    """Refuse a second patch before building one; e.g. ``ensure_unpatched(t)``."""
    if load_patch_record(target) is not None:
        raise ValueError(f"{target.exe.name}: already patched; revert it first")


def apply_exe_patch(
    target: ExePatchTarget, original: bytes, patched: bytes, description: str
) -> ExePatchRecord:
    """Back up, then replace the exe; e.g. ``apply_exe_patch(t, old, new, '3440x1440')``."""
    ensure_unpatched(target)
    if sha256_hex(target.exe.read_bytes()) != sha256_hex(original):
        raise ValueError(f"{target.exe.name}: changed while the patch was built")
    record = ExePatchRecord(
        str(target.exe), sha256_hex(original), sha256_hex(patched), description
    )
    _keep_original(target)
    _save_record(target, record)
    _write_atomically(target.exe, patched)
    return record


def _forget(target: ExePatchTarget) -> None:
    target.backup.unlink(missing_ok=True)
    target.record.unlink(missing_ok=True)


def _restore(target: ExePatchTarget, record: ExePatchRecord) -> None:
    original = target.backup.read_bytes()
    if sha256_hex(original) != record.original_sha256:
        raise ValueError(
            f"backup={str(target.backup)!r}: expected sha256 "
            f"{record.original_sha256}; verify the game files in Steam instead"
        )
    _write_atomically(target.exe, original)


def revert_exe_patch(target: ExePatchTarget) -> str:
    """Put the original back; e.g. ``revert_exe_patch(target)``."""
    record = load_patch_record(target)
    if record is None:
        raise ValueError(f"{target.exe.name}: expected an OmaMods patch record")
    current = sha256_hex(target.exe.read_bytes())
    if current == record.original_sha256:
        _forget(target)
        return f"{target.exe.name} was already the original; record cleared"
    if current != record.patched_sha256:
        raise ValueError(
            f"{target.exe.name} sha256={current}: expected the patched "
            f"{record.patched_sha256}; it changed since, so verify in Steam"
        )
    _restore(target, record)
    _forget(target)
    return f"{target.exe.name} restored to the original"


def _remove_empty_dirs(target: ExePatchTarget) -> None:
    for folder in (target.backup.parent, target.record.parent):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()


def remove_patch_files(target: ExePatchTarget) -> str:
    """Delete everything stored for the patch; e.g. ``remove_patch_files(t)``.

    A patched exe is restored first, since the backup is its only original.
    Without a record the exe was never replaced (apply writes the backup, then
    the record, then the exe), so a leftover backup is safe to delete.
    """
    if load_patch_record(target) is not None:
        message = revert_exe_patch(target)
    elif target.backup.exists():
        target.backup.unlink()
        message = f"{target.exe.name}: leftover backup deleted"
    else:
        message = f"{target.exe.name}: nothing stored to remove"
    _remove_empty_dirs(target)
    return message


def describe_patch_state(target: ExePatchTarget) -> str:
    """Summarise the exe; e.g. ``describe_patch_state(target)``."""
    record = load_patch_record(target)
    if record is None:
        return f"{target.exe.name}: not patched by OmaMods"
    current = sha256_hex(target.exe.read_bytes())
    if current == record.patched_sha256:
        return f"{target.exe.name}: patched ({record.description})"
    if current == record.original_sha256:
        return f"{target.exe.name}: original again; revert clears the record"
    return f"{target.exe.name}: changed since the patch ({record.description})"
