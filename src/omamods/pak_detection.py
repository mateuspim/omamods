"""Promote installed Unreal and RE Engine games with a Nexus page to mod-ready."""

from dataclasses import dataclass, replace

from omamods.filesystem import ReadableFiles
from omamods.game_shelf import MOD_READY, GameShelf, ShelfEntry, shelf_order
from omamods.installed_games import InstalledGame
from omamods.nexus_games import NexusGameDirectory
from omamods.pak_games import (
    IOSTORE_SUFFIXES,
    PAK_SUFFIXES,
    PakGameCatalog,
    PakOverlayGame,
)
from omamods.re_engine_detection import re_engine_domain, scanned_re_engine_game
from omamods.re_engine_layout import detect_patch_chain
from omamods.unreal_layout import UnrealLayout, detect_unreal_layout

# "~" sorts after every shipped pak, so the engine mounts mods last and they
# override base assets; most Unreal mod pages ask for this folder.
DEFAULT_MODS_DIRNAME = "~mods"


@dataclass
class _ClaimedIds:
    """Game IDs and domains already in use, so two entries never share one."""

    game_ids: set[str]
    domains: set[str]

    def take(self, game_id: str, domain: str) -> bool:
        if game_id in self.game_ids or domain in self.domains:
            return False
        self.game_ids.add(game_id)
        self.domains.add(domain)
        return True


def scanned_pak_game(
    game_id: str, install: InstalledGame, domain: str, layout: UnrealLayout
) -> PakOverlayGame:
    """Describe a found game; e.g. ``scanned_pak_game('remnant2', game, 'remnant2', layout)``."""
    # IoStore games still mount a legacy lone .pak, so accept both shapes.
    suffix_sets = (
        (PAK_SUFFIXES, IOSTORE_SUFFIXES) if layout.iostore else (PAK_SUFFIXES,)
    )
    return PakOverlayGame(
        game_id=game_id,
        name=install.name,
        nexus_domain=domain,
        paks_subpath=layout.paks_subpath,
        mods_dirname=DEFAULT_MODS_DIRNAME,
        flat_suffix_sets=suffix_sets,
        install_root=install.install_path,
        signed=layout.signed,
    )


def _titles(entry: ShelfEntry, install: InstalledGame) -> tuple[str, ...]:
    manifest = (entry.manifest.name,) if entry.manifest else ()
    return (*manifest, entry.name, install.name)


def _claimed_id(
    entry: ShelfEntry, domain: str | None, claimed: _ClaimedIds
) -> str | None:
    game_id = entry.manifest.id if entry.manifest else domain
    if domain is None or game_id is None or not claimed.take(game_id, domain):
        return None
    return game_id


def _promoted_re_engine(
    entry: ShelfEntry,
    install: InstalledGame,
    chain: str,
    directory: NexusGameDirectory,
    claimed: _ClaimedIds,
) -> ShelfEntry:
    domain = re_engine_domain(install, _titles(entry, install), directory)
    game_id = _claimed_id(entry, domain, claimed)
    if domain is None or game_id is None:
        return replace(entry, patch_chain=chain)
    game = scanned_re_engine_game(game_id, install, domain, chain)
    return replace(entry, section=MOD_READY, pak_game=game, patch_chain=chain)


def _promoted_unreal(
    entry: ShelfEntry,
    install: InstalledGame,
    layout: UnrealLayout,
    directory: NexusGameDirectory,
    claimed: _ClaimedIds,
) -> ShelfEntry:
    domain = directory.domain_for(*_titles(entry, install))
    game_id = _claimed_id(entry, domain, claimed)
    if domain is None or game_id is None:
        return replace(entry, unreal=layout)
    game = scanned_pak_game(game_id, install, domain, layout)
    return replace(entry, section=MOD_READY, pak_game=game, unreal=layout)


def _promoted(
    entry: ShelfEntry,
    files: ReadableFiles,
    directory: NexusGameDirectory,
    claimed: _ClaimedIds,
) -> ShelfEntry:
    install = entry.install
    if entry.section == MOD_READY or install is None or not install.ready:
        return entry
    chain = detect_patch_chain(install.install_path, files)
    if chain is not None:
        return _promoted_re_engine(entry, install, chain, directory, claimed)
    layout = detect_unreal_layout(install.install_path, files)
    if layout is None:
        return entry
    return _promoted_unreal(entry, install, layout, directory, claimed)


def promote_pak_games(
    shelf: GameShelf, files: ReadableFiles, directory: NexusGameDirectory
) -> GameShelf:
    """Make Unreal and RE Engine games mod-ready.

    Example: ``promote_pak_games(shelf, files, nexus)``.
    """
    builtins = PakGameCatalog().all()
    claimed = _ClaimedIds(
        {game.game_id for game in builtins}, {game.nexus_domain for game in builtins}
    )
    entries = (_promoted(e, files, directory, claimed) for e in shelf.entries)
    return replace(shelf, entries=tuple(sorted(entries, key=shelf_order)))


def scanned_pak_games(shelf: GameShelf) -> tuple[PakOverlayGame, ...]:
    """List games found by scanning; e.g. ``PakGameCatalog(scanned_pak_games(s))``."""
    return tuple(
        entry.pak_game
        for entry in shelf.entries
        if entry.pak_game is not None and entry.pak_game.install_root is not None
    )
