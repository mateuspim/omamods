"""Describe the staging folder: downloaded archives plus each mod's page details.

Layout under the storage root (archives keep their pre-TUI location so older
downloads stay staged)::

    archives/<game>/<mod_id>/mod.json
    archives/<game>/<mod_id>/picture.<ext>
    archives/<game>/<mod_id>/<file_id>/<file_name>
"""

from dataclasses import asdict, dataclass
import json
from pathlib import Path, PurePosixPath
from urllib import parse

from omamods.install_records import installed_file_ids
from omamods.mod_sites import NEXUS_SITE
from omamods.nexus_api import NexusFile, NexusModInfo
from omamods.pak_games import PakOverlayGame

PICTURE_SUFFIXES = frozenset({".gif", ".jpeg", ".jpg", ".png", ".webp"})


@dataclass(frozen=True)
class StagedMod:
    """Everything the TUI shows about one mod in the staging folder."""

    mod_id: int
    info: NexusModInfo | None
    files: tuple[NexusFile, ...]
    archives: dict[int, Path]
    picture: Path | None
    installed: frozenset[int]
    # Which site's numbering mod_id follows; Ayaka mods live in their own area.
    site: str = NEXUS_SITE

    @property
    def title(self) -> str:
        """Name for lists; for example, ``staged.title``."""
        return self.info.name if self.info else f"Mod {self.mod_id}"


def mod_folder(root: Path, game: PakOverlayGame, mod_id: int) -> Path:
    """Locate one mod's staging folder; e.g. ``mod_folder(root, sb, 1)``."""
    return root / "archives" / game.game_id / str(mod_id)


def picture_path(folder: Path, url: str) -> Path:
    """Name the cached main picture; e.g. ``picture_path(folder, 'https://x/a.png')``."""
    suffix = PurePosixPath(parse.urlparse(url).path).suffix.lower()
    return folder / f"picture{suffix if suffix in PICTURE_SUFFIXES else '.jpg'}"


def save_mod_details(
    folder: Path, info: NexusModInfo, files: tuple[NexusFile, ...]
) -> None:
    """Persist page details; e.g. ``save_mod_details(folder, info, files)``."""
    folder.mkdir(parents=True, exist_ok=True)
    details = {"info": asdict(info), "files": [asdict(item) for item in files]}
    temporary = folder / "mod.json.partial"
    temporary.write_text(json.dumps(details, indent=2), encoding="utf-8")
    temporary.replace(folder / "mod.json")


def load_mod_details(
    folder: Path,
) -> tuple[NexusModInfo | None, tuple[NexusFile, ...]]:
    """Read page details if fetched; e.g. ``load_mod_details(folder)``."""
    record = folder / "mod.json"
    if not record.is_file():
        return None, ()
    try:
        details = json.loads(record.read_text(encoding="utf-8"))
        info = NexusModInfo(**details["info"])
        files = tuple(NexusFile(**item) for item in details["files"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"mod details={str(record)!r}: expected info and files objects"
        ) from error
    return info, files


def staged_archives(folder: Path) -> dict[int, Path]:
    """Map file IDs to downloaded archives; e.g. ``staged_archives(folder)``."""
    archives: dict[int, Path] = {}
    for file_folder in sorted(folder.glob("*/")):
        archive = next(
            (p for p in sorted(file_folder.iterdir()) if _is_archive(p)), None
        )
        if file_folder.name.isdecimal() and archive is not None:
            archives[int(file_folder.name)] = archive
    return archives


def _is_archive(path: Path) -> bool:
    return path.is_file() and not path.name.startswith(".")


def _files_on_disk(archives: dict[int, Path]) -> tuple[NexusFile, ...]:
    # Hand-downloaded archives have no mod.json; describe them from disk.
    return tuple(
        NexusFile(file_id, path.name, "STAGED", 0) for file_id, path in archives.items()
    )


def load_staged_mod(root: Path, game: PakOverlayGame, mod_id: int) -> StagedMod:
    """Describe one staged mod; e.g. ``load_staged_mod(root, sb, 1)``."""
    folder = mod_folder(root, game, mod_id)
    info, files = load_mod_details(folder)
    archives = staged_archives(folder)
    known = {item.file_id for item in files}
    extra = tuple(f for f in _files_on_disk(archives) if f.file_id not in known)
    pictures = sorted(folder.glob("picture.*"))
    installed = installed_file_ids(root, game, mod_id)
    return StagedMod(
        mod_id, info, files + extra, archives, next(iter(pictures), None), installed
    )


def list_staged_mods(root: Path, game: PakOverlayGame) -> tuple[StagedMod, ...]:
    """Describe the game's staging folder; e.g. ``list_staged_mods(root, sb)``."""
    folder = root / "archives" / game.game_id
    mod_ids = sorted(
        int(path.name) for path in folder.glob("*/") if path.name.isdecimal()
    )
    return tuple(load_staged_mod(root, game, mod_id) for mod_id in mod_ids)


def remove_staged_archive(
    root: Path, game: PakOverlayGame, mod_id: int, file_id: int
) -> Path:
    """Delete one downloaded file; e.g. ``remove_staged_archive(root, sb, 365, 1028)``."""
    mod = load_staged_mod(root, game, mod_id)
    if file_id in mod.installed:
        raise ValueError(
            f"file_id={file_id}: expected an uninstalled file; uninstall it first"
        )
    archive = mod.archives.get(file_id)
    if archive is None:
        raise ValueError(f"file_id={file_id}: expected a staged archive to remove")
    archive.unlink()
    if not any(archive.parent.iterdir()):
        archive.parent.rmdir()
    return archive
