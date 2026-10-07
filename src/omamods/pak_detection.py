"""Promote installed Unreal games with a Nexus page to mod-ready shelf entries."""

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


def _promoted(
    entry: ShelfEntry,
    files: ReadableFiles,
    directory: NexusGameDirectory,
    claimed: _ClaimedIds,
) -> ShelfEntry:
    install = entry.install
    if entry.section == MOD_READY or install is None or not install.ready:
        return entry
    layout = detect_unreal_layout(install.install_path, files)
    if layout is None:
        return entry
    domain = directory.domain_for(*_titles(entry, install))
    game_id = entry.manifest.id if entry.manifest else domain
    if domain is None or game_id is None or not claimed.take(game_id, domain):
        return replace(entry, unreal=layout)
    game = scanned_pak_game(game_id, install, domain, layout)
    return replace(entry, section=MOD_READY, pak_game=game, unreal=layout)


def promote_unreal_games(
    shelf: GameShelf, files: ReadableFiles, directory: NexusGameDirectory
) -> GameShelf:
    """Make Unreal games mod-ready; e.g. ``promote_unreal_games(shelf, files, nexus)``."""
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
