"""Describe an installed RE Engine game as a pak game OmaMods can mod."""

from pathlib import Path

from omamods.installed_games import InstalledGame
from omamods.nexus_games import NexusGameDirectory
from omamods.pak_games import PAK_SUFFIXES, PakOverlayGame

# Steam names the RE Engine remakes like the originals ("Resident Evil 4"), so
# a title match picks the 2005 game's Nexus page; RE7's Steam title adds
# "Biohazard", which Nexus' "Resident Evil 7" lacks. Pin them by app ID.
RE_ENGINE_STEAM_DOMAINS: dict[str, str] = {
    "883710": "residentevil22019",
    "952060": "residentevil32020",
    "2050650": "residentevil42023",
    "418370": "residentevil7",
}


def re_engine_domain(
    install: InstalledGame, titles: tuple[str, ...], directory: NexusGameDirectory
) -> str | None:
    """Find the Nexus page; e.g. ``re_engine_domain(game, ('Resident Evil 4',), nexus)``."""
    if install.store == "Steam" and install.app_id in RE_ENGINE_STEAM_DOMAINS:
        return RE_ENGINE_STEAM_DOMAINS[install.app_id]
    return directory.domain_for(*titles)


def scanned_re_engine_game(
    game_id: str, install: InstalledGame, domain: str, chain: str
) -> PakOverlayGame:
    """Describe a found game; e.g. ``scanned_re_engine_game('re7', game, 're7', chain)``."""
    # Patches sit beside the base pak at the game root; no mods folder exists.
    return PakOverlayGame(
        game_id=game_id,
        name=install.name,
        nexus_domain=domain,
        paks_subpath=Path("."),
        mods_dirname="",
        flat_suffix_sets=(PAK_SUFFIXES,),
        install_root=install.install_path,
        patch_chain=chain,
    )
