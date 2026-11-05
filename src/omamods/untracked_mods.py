"""Find mod files in a game folder that no OmaMods install record owns.

After the storage folder is deleted or a mod was copied by hand, the files stay
in the game but OmaMods can no longer revert them; this lists them.
"""

from collections.abc import Iterable, Mapping
from dataclasses import replace
import json
from pathlib import Path

from omamods.game_shelf import GameShelf, ShelfEntry
from omamods.loose_mod_files import asi_loose_files, red_loose_files, ue4ss_loose_files
from omamods.pak_detection import scanned_pak_game
from omamods.pak_games import PakOverlayGame
from omamods.re_engine_detection import scanned_re_engine_game
from omamods.re_patch_chain import is_empty_patch

CONTAINER_SUFFIXES = frozenset({".pak", ".ucas", ".utoc", ".sig"})


def owned_paths(state_folder: Path) -> frozenset[Path]:
    """Read every file the records under a folder own; e.g. ``owned_paths(root / 'state' / 're7')``."""
    owned: set[Path] = set()
    for record in state_folder.rglob("*.json") if state_folder.is_dir() else ():
        owned.update(record_files(record))
    return frozenset(owned)


def record_files(record: Path) -> tuple[Path, ...]:
    """List the files one install record owns; e.g. ``record_files(state / '7' / '1.json')``."""
    try:
        state = json.loads(record.read_text(encoding="utf-8"))
        paks = Path(state["paks"])
        return tuple(paks / str(asset["relative_path"]) for asset in state["assets"])
    except (OSError, KeyError, TypeError, ValueError):
        return ()  # Config and chain records have another shape; they own no paks.


def mod_candidates(game: PakOverlayGame, paks: Path) -> tuple[Path, ...]:
    """List files that look like mods; e.g. ``mod_candidates(game, paks)``."""
    if game.patch_chain is not None:
        patches = paks.glob(f"{game.patch_chain}.patch_*.pak")
        # RE7 ships 0-byte placeholder patches; they are the game's, not mods.
        return tuple(sorted(p for p in patches if not is_empty_patch(p)))
    if game.redengine:
        return red_loose_files(paks)
    if game.asi_loader:
        return asi_loose_files(paks)
    if game.mods_dirname in ("", "."):
        # The game's own files mix with mods there; no safe filter exists.
        return ()
    return _unreal_candidates(game, paks)


def _unreal_candidates(game: PakOverlayGame, paks: Path) -> tuple[Path, ...]:
    folder = paks / game.mods_dirname
    found: list[Path] = []
    if folder.is_dir():
        found = [p for p in folder.rglob("*") if p.suffix.lower() in CONTAINER_SUFFIXES]
    loose = (*ue4ss_loose_files(paks), *_logic_mods(paks))
    return tuple(sorted({*(p for p in found if p.is_file()), *loose}))


def _logic_mods(paks: Path) -> tuple[Path, ...]:
    # UE4SS blueprint mods load from Paks/LogicMods, beside the mods folder.
    folder = paks / "LogicMods"
    found = folder.rglob("*") if folder.is_dir() else ()
    return tuple(p for p in found if p.suffix.lower() in CONTAINER_SUFFIXES)


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
    if install is None or not install.ready:
        return entry.pak_game
    if entry.pak_game is not None:
        # Built-in games carry no install_root, so the audit skipped them all.
        return _rooted(entry.pak_game, install.install_path)
    if entry.patch_chain is not None:
        return scanned_re_engine_game(entry.key, install, "", entry.patch_chain)
    if entry.unreal is not None:
        return scanned_pak_game(entry.key, install, "", entry.unreal)
    return None


def _rooted(game: PakOverlayGame, install_path: Path) -> PakOverlayGame:
    if game.install_root is not None:
        return game
    return replace(game, install_root=install_path)


def audit_shelf(shelf: GameShelf, roots: Iterable[Path]) -> dict[str, tuple[Path, ...]]:
    """Map shelf keys to mod files without records; e.g. ``audit_shelf(shelf, (root,))``."""
    return audit_keyed(shelf_pak_games(shelf), roots)


def audit_keyed(
    games: Mapping[str, PakOverlayGame], roots: Iterable[Path]
) -> dict[str, tuple[Path, ...]]:
    """Map shelf keys to mod files without records; e.g. ``audit_keyed(games, (root,))``."""
    roots = tuple(roots)
    found: dict[str, tuple[Path, ...]] = {}
    for key, game in games.items():
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
