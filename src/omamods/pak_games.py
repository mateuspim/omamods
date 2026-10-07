"""Describe games whose self-contained pak mods share one installer.

Unreal games overlay a mods folder; RE Engine games load numbered patch paks.
"""

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
    # Set for games found by scanning instead of listed here; their folder is
    # known from the launcher, so no catalog manifest is needed to find Paks.
    install_root: Path | None = None
    # Shipped .sig files mean the game may refuse unsigned mod paks.
    signed: bool = False
    # RE Engine games load mods as numbered patches of this base pak, e.g.
    # re_chunk_000.pak.patch_009.pak, instead of from a mods folder.
    patch_chain: str | None = None


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
    """Look up a built-in game; e.g. ``pak_overlay_game('stellar-blade')``."""
    return PakGameCatalog().get(game_id)


class PakGameCatalog:
    """Built-in games plus any found by scanning; e.g. ``PakGameCatalog().get('cronos')``."""

    def __init__(self, detected: tuple[PakOverlayGame, ...] = ()) -> None:
        self.games: dict[str, PakOverlayGame] = {}
        for game in detected:
            self.games.setdefault(game.game_id, game)
        # Built-ins carry hand-checked settings, so they win over a scan.
        self.games.update(PAK_OVERLAY_GAMES)

    def all(self) -> tuple[PakOverlayGame, ...]:
        """List every game; for example, ``catalog.all()``."""
        return tuple(self.games.values())

    def get(self, game_id: str) -> PakOverlayGame:
        """Look up by ID; for example, ``catalog.get('atomicheart')``."""
        game = self.games.get(game_id)
        if game is None:
            raise ValueError(
                f"game={game_id!r}: expected one of {sorted(self.games)!r}"
            )
        return game

    def for_domain(self, domain: str) -> PakOverlayGame:
        """Map a Nexus domain; for example, ``catalog.for_domain('stellarblade')``."""
        for game in self.games.values():
            if game.nexus_domain == domain:
                return game
        supported = sorted(game.nexus_domain for game in self.games.values())
        raise ValueError(f"Nexus domain={domain!r}: expected one of {supported!r}")
