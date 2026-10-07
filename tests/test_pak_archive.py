"""Exercise archive layouts for Cronos and Stellar Blade asset mods."""

from dataclasses import replace
from pathlib import Path
import unittest

from omamods.pak_archive import plan_pak_assets, variant_folders
from omamods.pak_games import PAK_OVERLAY_GAMES, pak_overlay_game

CRONOS = PAK_OVERLAY_GAMES["cronos"]
STELLAR_BLADE = PAK_OVERLAY_GAMES["stellar-blade"]
CLAIR_OBSCUR = replace(
    STELLAR_BLADE,
    game_id="clairobscurexpedition33",
    name="Clair Obscur: Expedition 33",
    paks_subpath=Path("Sandfall/Content/Paks"),
)
SUFFIXES = ("pak", "ucas", "utoc")


def targets(members: tuple[str, ...], option: str | None = None) -> list[Path]:
    return [a.target for a in plan_pak_assets(members, STELLAR_BLADE, option)]


def outfit_set_members() -> tuple[str, ...]:
    """Shaped like a real Clair Obscur outfit mod: shared Addons per
    character, then armor/no+armor x colour alternatives of one outfit."""
    members: list[str] = []
    for who in ("hero", "knight"):
        name = who.capitalize()
        members += [f"SuitCollection/{who}/{name}_Addons_P.{s}" for s in SUFFIXES]
        for kind in ("armor", "no+armor"):
            for colour in ("black", "blue", "red"):
                folder = f"SuitCollection/{who}/{kind}/{colour}"
                members += [f"{folder}/{name}_B_P.{s}" for s in SUFFIXES]
    return (*members, "SuitCollection/_0_Patch_SuitPack.zip")


class PakGameTests(unittest.TestCase):
    def test_lookup_rejects_unsupported_game(self) -> None:
        self.assertEqual(pak_overlay_game("stellar-blade").nexus_domain, "stellarblade")
        with self.assertRaisesRegex(ValueError, "expected one of"):
            pak_overlay_game("dawnwalker")


class StellarBladeLayoutTests(unittest.TestCase):
    def test_lone_flat_pak_goes_to_tilde_mods(self) -> None:
        self.assertEqual(
            targets(("Suit_P.pak", "readme.txt")), [Path("~mods/Suit_P.pak")]
        )

    def test_flat_triplet_goes_to_tilde_mods(self) -> None:
        members = ("a_P.pak", "a_P.utoc", "a_P.ucas")
        self.assertEqual(len(targets(members)), 3)

    def test_several_flat_triplets_install_together(self) -> None:
        # Regression: an outfit pack ships one loose triplet per outfit.
        members = tuple(
            f"{stem}_P.{suffix}"
            for stem in ("BlackNails", "Red Passion", "Planet Diving Suit (2nd)")
            for suffix in ("pak", "ucas", "utoc")
        )
        self.assertEqual(
            sorted(targets(members)), sorted(Path("~mods") / m for m in members)
        )

    def test_one_incomplete_set_rejects_the_pack_and_names_it(self) -> None:
        members = ("a_P.pak", "a_P.ucas", "a_P.utoc", "b_P.ucas", "b_P.utoc")
        with self.assertRaisesRegex(ValueError, r"incomplete: \['b_P'\]"):
            targets(members)

    def test_existing_tilde_mods_folder_is_anchor(self) -> None:
        self.assertEqual(
            targets(("Pack/~Mods/Hair/h.pak",)), [Path("~mods/Hair/h.pak")]
        )

    def test_single_folder_is_kept_intact(self) -> None:
        self.assertEqual(
            targets(("Sample Outfit/s.pak", "Sample Outfit/s.utoc")),
            [Path("~mods/Sample Outfit/s.pak"), Path("~mods/Sample Outfit/s.utoc")],
        )

    def test_several_variants_require_an_option(self) -> None:
        members = ("Mod/Black/s.pak", "Mod/White/s.pak")
        with self.assertRaisesRegex(ValueError, "Mod/Black.*set option"):
            targets(members)
        self.assertEqual(targets(members, "White"), [Path("~mods/White/s.pak")])
        self.assertEqual(targets(members, "Mod/Black"), [Path("~mods/Black/s.pak")])
        with self.assertRaisesRegex(ValueError, "option='Red'"):
            targets(members, "Red")

    def test_variant_installs_with_the_paks_above_it(self) -> None:
        members = (*outfit_set_members(), "SuitCollection/....txt")
        option = "SuitCollection/hero/armor/black"
        planned = plan_pak_assets(members, CLAIR_OBSCUR, option)
        self.assertEqual(
            sorted(asset.target for asset in planned),
            sorted(
                [Path("~mods/hero") / f"Hero_Addons_P.{s}" for s in SUFFIXES]
                + [Path("~mods/hero/armor/black") / f"Hero_B_P.{s}" for s in SUFFIXES]
            ),
        )

    def test_only_innermost_folders_are_variants(self) -> None:
        # Regression: a mod offered the shared Addons folders as
        # variants beside the outfits, and kept only 'black' as the folder.
        variants = variant_folders(outfit_set_members(), CLAIR_OBSCUR)
        self.assertEqual(len(variants), 12)
        self.assertNotIn("SuitCollection/hero", variants)
        self.assertIn("SuitCollection/knight/no+armor/red", variants)

    def test_a_lone_variant_installs_with_shared_paks_without_an_option(self) -> None:
        members = ("Mod/base.pak", "Mod/Red/r.pak")
        self.assertEqual(variant_folders(members, STELLAR_BLADE), ())
        self.assertEqual(
            targets(members), [Path("~mods/Mod/base.pak"), Path("~mods/Mod/Red/r.pak")]
        )

    def test_loader_dependent_archives_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "loaders and scripts"):
            targets(("~mods/a.pak", "Binaries/Win64/dwmapi.dll"))
        with self.assertRaisesRegex(ValueError, "loaders and scripts"):
            targets(("ue4ss/Mods/x/main.lua.txt", "a.pak"))

    def test_archives_without_paks_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected .pak assets"):
            targets(("readme.txt",))
        with self.assertRaisesRegex(ValueError, "at least one .pak"):
            targets(("Mod/a.utoc",))


class CronosLayoutRegressionTests(unittest.TestCase):
    def test_mod_38_archive_still_maps_into_mods(self) -> None:
        members = (
            "sample_mod_P.ucas",
            "sample_mod_P.utoc",
            "sample_mod_P.pak",
        )
        planned = plan_pak_assets(members, CRONOS, None)
        self.assertEqual(
            sorted(a.target for a in planned),
            sorted(Path("Mods") / m for m in members),
        )

    def test_cronos_rejects_lone_flat_pak(self) -> None:
        with self.assertRaisesRegex(ValueError, "same-stem"):
            plan_pak_assets(("a.pak",), CRONOS, None)


if __name__ == "__main__":
    unittest.main()
