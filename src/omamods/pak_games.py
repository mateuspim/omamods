"""Describe games whose self-contained Unreal asset mods share one installer."""

from dataclasses import dataclass
from pathlib import Path

PAK_SUFFIXES = frozenset({".pak"})
IOSTORE_SUFFIXES = frozenset({".pak", ".ucas", ".utoc"})


@dataclass(frozen=True)
class PakOverlayGame:
    """Where one game's Nexus asset mods come from and where they land."""

    game_id: str
    name: str
    nexus_domain: str
    paks_subpath: Path
    mods_dirname: str
    flat_suffix_sets: tuple[frozenset[str], ...]


PAK_OVERLAY_GAMES: dict[str, PakOverlayGame] = {
    "cronos": PakOverlayGame(
        game_id="cronos",
        name="Cronos",
        nexus_domain="cronosthenewdawn",
        paks_subpath=Path("Cronos/Content/Paks"),
        mods_dirname="Mods",
        # Mod 38's current ZIP is one flat same-stem triplet.
        flat_suffix_sets=(IOSTORE_SUFFIXES,),
    ),
    "stellar-blade": PakOverlayGame(
        game_id="stellar-blade",
        name="Stellar Blade",
        nexus_domain="stellarblade",
        paks_subpath=Path("SB/Content/Paks"),
        mods_dirname="~mods",
        # Stellar Blade mod 1 ships a lone .pak; others ship a triplet.
        flat_suffix_sets=(PAK_SUFFIXES, IOSTORE_SUFFIXES),
    ),
}


def pak_overlay_game(game_id: str) -> PakOverlayGame:
    """Look up a supported game; e.g. ``pak_overlay_game('stellar-blade')``."""
    game = PAK_OVERLAY_GAMES.get(game_id)
    if game is None:
        raise ValueError(
            f"game={game_id!r}: expected one of {sorted(PAK_OVERLAY_GAMES)!r}"
        )
    return game
