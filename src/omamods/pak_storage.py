"""Persist downloaded archives and reversible Unreal asset ownership."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from omamods.cdn_download import (
    ProgressCallback,
    RetryPolicy,
    download_with_retries,
)
from omamods.nexus_api import NexusFile, NexusTransport
from omamods.pak_archive import ASSET_SUFFIXES, ArchiveReader, PlannedAsset
from omamods.pak_games import PakOverlayGame
from omamods.red_archive import is_red_game_path, is_removable_red_folder
from omamods.re_pak_archive import write_packed_pak
from omamods.re_patch_chain import is_empty_patch, patch_number

PARTIAL_SUFFIX = ".partial"


@dataclass(frozen=True)
class InstalledAsset:
    """A newly created game file and its recorded digest."""

    relative_path: str
    sha256: str
    # The install overwrote an empty RE Engine patch; revert puts a 0-byte
    # file back instead of deleting, so Steam's file list still matches.
    replaced_empty: bool = False


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_path(
    root: Path, game: PakOverlayGame, mod_id: int, file: NexusFile
) -> Path:
    """Name persistent downloads; e.g. ``archive_path(root, cronos, 38, file)``."""
    folder = root / "archives" / game.game_id / str(mod_id) / str(file.file_id)
    return folder / file.file_name


def download_archive(
    destination: Path,
    file: NexusFile,
    uri: str,
    transport: NexusTransport,
    progress: ProgressCallback | None = None,
    retry: RetryPolicy = RetryPolicy(),
) -> Path:
    """Cache a complete archive; e.g. ``download_archive(path, file, uri, http)``."""
    if destination.is_file() and destination.stat().st_size:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The dot prefix and suffix keep staging listings from showing partial files.
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=".", suffix=PARTIAL_SUFFIX, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            download_with_retries(transport, uri, stream, progress, retry)
        except BaseException:
            temporary.unlink(missing_ok=True)
            _remove_if_empty(destination.parent)
            raise
    if not temporary.stat().st_size:
        temporary.unlink()
        raise ValueError(f"Nexus file={file.file_name!r}: expected a nonempty archive")
    os.replace(temporary, destination)
    return destination


def _remove_if_empty(folder: Path) -> None:
    # A failed first download must not leave an empty file folder in staging.
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()


def cache_downloaded_archive(destination: Path, source: Path) -> Path:
    """Retain a supplied archive; e.g. ``cache_downloaded_archive(path, zip)``."""
    if destination.exists():
        if _digest(destination) != _digest(source):
            raise ValueError(
                f"archive={str(destination)!r}: expected the same cached SHA-256"
            )
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with destination.open("xb") as outgoing:
            created = True
            with source.open("rb") as incoming:
                shutil.copyfileobj(incoming, outgoing)
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    if not destination.stat().st_size:
        destination.unlink()
        raise ValueError(f"archive={str(source)!r}: expected nonempty content")
    return destination


def _safe_target(paks: Path, relative: Path) -> Path:
    target = paks / relative
    if not target.parent.resolve().is_relative_to(paks.resolve()):
        raise ValueError(f"asset target={str(target)!r}: expected a path beneath Paks/")
    if target.is_symlink():
        raise ValueError(f"asset target={str(target)!r}: expected a regular path")
    return target


def _preflight(paks: Path, assets: tuple[PlannedAsset, ...], record: Path) -> None:
    if not paks.is_dir():
        raise ValueError(f"Paks={str(paks)!r}: expected an installed game directory")
    if record.exists():
        raise ValueError(
            f"install state={str(record)!r}: expected no existing installation; revert first"
        )
    for asset in assets:
        target = _safe_target(paks, asset.target)
        if target.exists() and not (asset.replaces_empty and is_empty_patch(target)):
            raise ValueError(
                f"asset target={str(target)!r}: expected an unowned path; the file "
                "already exists, so revert the mod that installed it first"
            )


def _write_asset(
    archive: Path, paks: Path, asset: PlannedAsset, reader: ArchiveReader
) -> InstalledAsset:
    target = _safe_target(paks, asset.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if asset.replaces_empty:
        target.unlink(missing_ok=True)  # Preflight checked that it holds no files.
    created = False
    try:
        with target.open("xb") as stream:
            created = True
            if asset.packed:
                write_packed_pak(archive, asset, stream, reader)
            else:
                reader.copy_member(archive, asset.member, stream)
    except BaseException:
        if created:
            target.unlink()
        raise
    if not asset.allow_empty and not target.stat().st_size:
        target.unlink()
        raise ValueError(f"asset member={asset.member!r}: expected nonempty content")
    return InstalledAsset(
        asset.target.as_posix(), _digest(target), asset.replaces_empty
    )


def _write_state(
    record: Path,
    paks: Path,
    archive: Path,
    file_id: int,
    assets: tuple[InstalledAsset, ...],
) -> None:
    state = {
        "paks": str(paks.resolve()),
        "archive_sha256": _digest(archive),
        "file_id": file_id,
        "assets": [vars(asset) for asset in assets],
    }
    record.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=record.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(state, stream, indent=2)
    try:
        os.link(temporary, record)
    finally:
        temporary.unlink(missing_ok=True)


def install_pak_archive(
    archive: Path,
    paks: Path,
    record: Path,
    file_id: int,
    reader: ArchiveReader,
    planned: tuple[PlannedAsset, ...],
) -> tuple[InstalledAsset, ...]:
    """Install owned files; e.g. ``install_pak_archive(zip, paks, state, 12, reader, plan)``."""
    _preflight(paks, planned, record)
    created: list[Path] = []
    folders: list[Path] = []
    installed: list[InstalledAsset] = []
    try:
        for asset in planned:
            target = paks / asset.target
            folders.extend(_missing_folders(paks, target))
            installed.append(_write_asset(archive, paks, asset, reader))
            created.append(target)
        _write_state(record, paks, archive, file_id, tuple(installed))
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        _remove_new_folders(folders)
        _restore_empty_patches(paks, planned)
        raise
    return tuple(installed)


def _missing_folders(paks: Path, target: Path) -> list[Path]:
    # Deepest first, so a rollback can remove them in this order.
    missing: list[Path] = []
    folder = target.parent
    while folder != paks and not folder.exists():
        missing.append(folder)
        folder = folder.parent
    return missing


def _remove_new_folders(folders: list[Path]) -> None:
    # A failed install left r6/config/redsUserHints/ behind (ArchiveXL 1.27.4).
    for folder in sorted(set(folders), key=lambda f: len(f.parts), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()


def _restore_empty_patches(paks: Path, planned: tuple[PlannedAsset, ...]) -> None:
    for asset in planned:
        target = paks / asset.target
        if asset.replaces_empty and not target.exists():
            target.touch()


def _recorded_assets(
    record: Path, game: PakOverlayGame
) -> tuple[Path, tuple[InstalledAsset, ...]]:
    try:
        state = json.loads(record.read_text(encoding="utf-8"))
        paks = Path(state["paks"])
        assets = tuple(InstalledAsset(**item) for item in state["assets"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"install state={str(record)!r}: expected a valid ownership record"
        ) from error
    if not paks.is_absolute() or not assets:
        raise ValueError(
            f"install state={str(record)!r}: expected Paks path and owned assets"
        )
    if len({asset.relative_path for asset in assets}) != len(assets):
        raise ValueError(
            f"install state={str(record)!r}: expected unique owned asset paths"
        )
    for asset in assets:
        _validate_owned_path(asset, game)
        _validate_digest(asset)
    return paks, assets


def _validate_owned_path(asset: InstalledAsset, game: PakOverlayGame) -> None:
    if game.patch_chain is not None:
        _validate_owned_patch(asset, game.patch_chain)
        return
    if game.redengine:
        _validate_owned_game_path(asset)
        return
    mods_dirname = game.mods_dirname
    relative = Path(asset.relative_path)
    if (
        relative.is_absolute()
        or len(relative.parts) < 2
        or relative.parts[0] != mods_dirname
        or ".." in relative.parts
        or relative.suffix.lower() not in ASSET_SUFFIXES
    ):
        raise ValueError(
            f"owned asset={asset.relative_path!r}: expected a path beneath {mods_dirname}/"
        )


def _validate_owned_game_path(asset: InstalledAsset) -> None:
    if not is_red_game_path(asset.relative_path):
        raise ValueError(
            f"owned asset={asset.relative_path!r}: expected a path beneath a "
            "game folder such as bin/ or archive/"
        )


def _validate_owned_patch(asset: InstalledAsset, chain: str) -> None:
    if patch_number(chain, asset.relative_path) is None:
        raise ValueError(
            f"owned asset={asset.relative_path!r}: expected {chain}.patch_NNN.pak"
        )


def _validate_digest(asset: InstalledAsset) -> None:
    if len(asset.sha256) != 64 or any(
        c not in "0123456789abcdef" for c in asset.sha256
    ):
        raise ValueError(
            f"owned SHA-256={asset.sha256!r}: expected 64 lowercase hex digits"
        )


def revert_pak_mod(record: Path, game: PakOverlayGame) -> tuple[Path, ...]:
    """Remove unchanged owned files; for example, ``revert_pak_mod(record, game)``.

    RE Engine callers then run ``fill_patch_gaps`` on every removed patch.
    """
    paks, assets = _recorded_assets(record, game)
    targets = tuple(_safe_target(paks, Path(asset.relative_path)) for asset in assets)
    for target, asset in zip(targets, assets, strict=True):
        if target.exists() and _digest(target) != asset.sha256:
            raise ValueError(
                f"asset target={str(target)!r}: expected original SHA-256; file changed"
            )
    for target, asset in zip(targets, assets, strict=True):
        target.unlink(missing_ok=True)
        if asset.replaced_empty:
            target.touch()
    if game.redengine:
        _prune_empty_folders(paks, targets)
    record.unlink()
    return targets


def _prune_empty_folders(root: Path, targets: tuple[Path, ...]) -> None:
    # Framework folders such as red4ext/plugins/ArchiveXL would otherwise stay
    # behind empty; the game's own top-level folders are never removed.
    for target in targets:
        folder = target.parent
        while is_removable_red_folder(root, folder):
            folder.rmdir()
            folder = folder.parent
