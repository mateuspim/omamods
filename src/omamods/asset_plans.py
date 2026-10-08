"""Pick the archive planner that matches a game's engine."""

from omamods.pak_archive import PlannedAsset, plan_pak_assets, variant_folders
from omamods.pak_games import PakOverlayGame
from omamods.red_archive import plan_red_archives, red_archive_variants
from omamods.re_pak_archive import patch_pak_variants, plan_patch_paks


def plan_game_assets(
    members: tuple[str, ...], game: PakOverlayGame, option: str | None
) -> tuple[PlannedAsset, ...]:
    """Plan for Unreal, RE Engine, or REDengine; e.g. ``plan_game_assets(names, re7, None)``."""
    if game.redengine:
        return plan_red_archives(members, game, option)
    if game.patch_chain is not None:
        return plan_patch_paks(members, game, option)
    return plan_pak_assets(members, game, option)


def game_variants(members: tuple[str, ...], game: PakOverlayGame) -> tuple[str, ...]:
    """List variant folders for any engine; e.g. ``game_variants(names, re7)``."""
    if game.redengine:
        return red_archive_variants(members, game)
    if game.patch_chain is not None:
        return patch_pak_variants(members)
    return variant_folders(members, game)
