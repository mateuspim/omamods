"""Stage AyakaMods mods in their own storage area, beside Nexus' staging.

AyakaMods and Nexus number their mods independently, so Ayaka mods keep the
same layout under ``<storage-root>/ayaka/`` (archives and install records)
and their IDs can never meet Nexus ones::

    ayaka/archives/<game>/<mod_id>/mod.json
    ayaka/archives/<game>/<mod_id>/<n>/<file_name>
    ayaka/state/<game>/<mod_id>/<n>.json
"""

from pathlib import Path

from omamods.ayaka_pages import (
    AyakaModDetails,
    AyakaPage,
    AyakaPageTransport,
    fetch_mod_details,
)
from omamods.download_watch import claim_download
from omamods.mod_fetch import stage_picture
from omamods.nexus_api import NexusFile, NexusTransport
from omamods.nexus_games import title_keys
from omamods.pak_games import PakOverlayGame
from omamods.staging import (
    StagedMod,
    load_mod_details,
    load_staged_mod,
    mod_folder,
    save_mod_details,
    staged_archives,
)

AYAKA_FOLDER = "ayaka"
# Ayaka pages offer one download, not Nexus' categorised file list.
AYAKA_FILE_CATEGORY = "MAIN"


def ayaka_root(storage_root: Path) -> Path:
    """Locate Ayaka's storage area; e.g. ``ayaka_root(Path('~/.local/share/omamods'))``."""
    return storage_root / AYAKA_FOLDER


def require_game(details: AyakaModDetails, game: PakOverlayGame) -> None:
    """Refuse mods for another game; e.g. ``require_game(details, clair_obscur)``."""
    if set(title_keys(details.game_name)) & set(title_keys(game.name)):
        return
    raise ValueError(
        f"AyakaMods mod {details.info.name!r} is for game={details.game_name!r}: "
        f"expected {game.name!r}"
    )


def stage_ayaka_details(
    pages: AyakaPageTransport,
    pictures: NexusTransport,
    game: PakOverlayGame,
    page: AyakaPage,
    root: Path,
) -> StagedMod:
    """Save page details and picture; e.g. ``stage_ayaka_details(http, cdn, co, page, root)``."""
    details = fetch_mod_details(pages, page)
    require_game(details, game)
    folder = mod_folder(root, game, page.mod_id)
    _, files = load_mod_details(folder)  # Keep files that already arrived.
    save_mod_details(folder, details.info, files)
    stage_picture(pictures, folder, details.info)
    return load_staged_mod(root, game, page.mod_id)


def _next_file_id(folder: Path, files: tuple[NexusFile, ...]) -> int:
    used = {file.file_id for file in files} | set(staged_archives(folder))
    return max(used, default=0) + 1


def claim_ayaka_archive(
    root: Path, game: PakOverlayGame, mod_id: int, archive: Path
) -> NexusFile:
    """Move a browser download into the mod's staging; e.g. ``claim_ayaka_archive(root, co, 7311, zip)``."""
    folder = mod_folder(root, game, mod_id)
    info, files = load_mod_details(folder)
    file_id = _next_file_id(folder, files)
    staged = claim_download(archive, folder / str(file_id))
    file = NexusFile(
        file_id, staged.name, AYAKA_FILE_CATEGORY, int(staged.stat().st_mtime)
    )
    if info is not None:
        save_mod_details(folder, info, files + (file,))
    return file
