"""Find mod files in a game folder that no OmaMods install record owns.

After the storage folder is deleted or a mod was copied by hand, the files stay
in the game but OmaMods can no longer revert them; this lists them.
"""

from collections.abc import Iterable
import json
from pathlib import Path

from omamods.game_shelf import GameShelf, ShelfEntry
from omamods.pak_detection import scanned_pak_game
from omamods.pak_games import PakOverlayGame
from omamods.re_engine_detection import scanned_re_engine_game
from omamods.re_patch_chain import is_empty_patch

CONTAINER_SUFFIXES = frozenset({".pak", ".ucas", ".utoc", ".sig"})


def owned_paths(state_folder: Path) -> frozenset[Path]:
    """Read every file the records under a folder own; e.g. ``owned_paths(root / 'state' / 're7')``."""
    owned: set[Path] = set()
    for record in state_folder.rglob("*.json") if state_folder.is_dir() else ():
        owned.update(_record_paths(record))
    return frozenset(owned)


def _record_paths(record: Path) -> tuple[Path, ...]:
    try:
        state = json.loads(record.read_text(encoding="utf-8"))
        paks = Path(state["paks"])
        return tuple(paks / str(asset["relative_path"]) for asset in state["assets"])
    except (OSError, KeyError, TypeError, ValueError):
        return ()  # Config and chain records have another shape; they own no paks.


def mod_candidates(game: PakOverlayGame, paks: Path) -> tuple[Path, ...]:
    """List files that look like mods; e.g. ``mod_candidates(game, paks)``."""
    if game.redengine or game.asi_loader or game.mods_dirname in ("", "."):
        # The game's own files mix with mods there; no safe filter exists.
        if game.patch_chain is None:
            return ()
    if game.patch_chain is not None:
        patches = paks.glob(f"{game.patch_chain}.patch_*.pak")
        # RE7 ships 0-byte placeholder patches; they are the game's, not mods.
        return tuple(sorted(p for p in patches if not is_empty_patch(p)))
    folder = paks / game.mods_dirname if game.mods_dirname else paks
    if not folder.is_dir():
        return ()
    found = (p for p in folder.rglob("*") if p.suffix.lower() in CONTAINER_SUFFIXES)
    return tuple(sorted(p for p in found if p.is_file()))


def untracked_mod_files(
    game: PakOverlayGame, paks: Path, owned: frozenset[Path]
) -> tuple[Path, ...]:
    """List mod files without a record; e.g. ``untracked_mod_files(game, paks, owned)``."""
    return tuple(path for path in mod_candidates(game, paks) if path not in owned)


def shelf_pak_games(shelf: GameShelf) -> dict[str, PakOverlayGame]:
    """Describe every installed Unreal or RE Engine game, matched or not; e.g. ``shelf_pak_games(shelf)``.

    Games with no Nexus page still keep mods in the same folders, so they get a
    stand-in description keyed by their shelf key.
    """
    games: dict[str, PakOverlayGame] = {}
    for entry in shelf.entries:
        game = _entry_game(entry)
        if game is not None:
            games[entry.key] = game
    return games


def _entry_game(entry: ShelfEntry) -> PakOverlayGame | None:
    install = entry.install
    if entry.pak_game is not None:
        return entry.pak_game
    if install is None or not install.ready:
        return None
    if entry.patch_chain is not None:
        return scanned_re_engine_game(entry.key, install, "", entry.patch_chain)
    if entry.unreal is not None:
        return scanned_pak_game(entry.key, install, "", entry.unreal)
    return None


def audit_shelf(shelf: GameShelf, roots: Iterable[Path]) -> dict[str, tuple[Path, ...]]:
    """Map shelf keys to mod files without records; e.g. ``audit_shelf(shelf, (root,))``."""
    roots = tuple(roots)
    found: dict[str, tuple[Path, ...]] = {}
    for key, game in shelf_pak_games(shelf).items():
        files = audit_games([game], roots).get(game.game_id, ())
        if files:
            found[key] = files
    return found


def audit_games(
    games: Iterable[PakOverlayGame], roots: Iterable[Path]
) -> dict[str, tuple[Path, ...]]:
    """Map game IDs to mod files without records; e.g. ``audit_games(games, (root,))``."""
    roots = tuple(roots)
    found: dict[str, tuple[Path, ...]] = {}
    for game in games:
        if game.install_root is None:
            continue
        state = (root / "state" / game.game_id for root in roots)
        owned = frozenset().union(*(owned_paths(folder) for folder in state))
        paks = game.install_root / game.paks_subpath
        files = untracked_mod_files(game, paks, owned)
        if files:
            found[game.game_id] = files
    return found
