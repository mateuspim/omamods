"""Name the games whose executables OmaMods patches, and how to build each.

A patch is computed from the game's own exe, so there is nothing to download;
each entry turns the untouched exe and the user's option (a resolution) into
the patched bytes and a short description for the record.
"""

from collections.abc import Callable
from dataclasses import dataclass

from omamods.mgr_ultrawide import EXE_NAME, build_ultrawide_exe, parse_resolution


@dataclass(frozen=True)
class ExePatchGame:
    """One catalog game with a built-in executable patch."""

    game_id: str
    name: str
    exe_name: str
    option_help: str
    build: Callable[[bytes, str], bytes]

    def describe(self, option: str) -> str:
        """Label a patch for its record; e.g. ``game.describe('3440x1440')``."""
        return f"{self.name} ultrawide {option}"


def _build_mgr(image: bytes, option: str) -> bytes:
    return build_ultrawide_exe(image, parse_resolution(option))


EXE_PATCH_GAMES: dict[str, ExePatchGame] = {
    "metalgearrising": ExePatchGame(
        game_id="metalgearrising",
        name="METAL GEAR RISING: REVENGEANCE",
        exe_name=EXE_NAME,
        option_help="display resolution WIDTHxHEIGHT, 16:9 or wider, e.g. 3440x1440",
        build=_build_mgr,
    ),
}


def exe_patch_game(game_id: str) -> ExePatchGame:
    """Look one up; e.g. ``exe_patch_game('metalgearrising')``."""
    game = EXE_PATCH_GAMES.get(game_id)
    if game is None:
        raise ValueError(
            f"game={game_id!r}: expected one of {sorted(EXE_PATCH_GAMES)!r}"
        )
    return game
