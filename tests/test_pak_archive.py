"""Exercise archive layouts for Cronos and Stellar Blade asset mods."""

from pathlib import Path
import unittest

from omamods.pak_archive import plan_pak_assets
from omamods.pak_games import PAK_OVERLAY_GAMES, pak_overlay_game

CRONOS = PAK_OVERLAY_GAMES["cronos"]
STELLAR_BLADE = PAK_OVERLAY_GAMES["stellar-blade"]


def targets(members: tuple[str, ...], option: str | None = None) -> list[Path]:
    return [a.target for a in plan_pak_assets(members, STELLAR_BLADE, option)]


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
