"""Pick container names that Unreal loads over the mods they clash with."""

import unittest

from omamods.asset_collisions import load_rank
from omamods.load_priority import container_base, outranks_all, priority_name


class ContainerBaseTests(unittest.TestCase):
    def test_strips_patch_suffixes(self) -> None:
        self.assertEqual(container_base("Fix_P"), "Fix")
        self.assertEqual(container_base("Mod_3_p"), "Mod")
        self.assertEqual(container_base("Plain"), "Plain")

    def test_refuses_names_without_a_base(self) -> None:
        for name in ("_P", "_2_P", "a/b_P"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "expected a file stem"):
                    container_base(name)


class PriorityNameTests(unittest.TestCase):
    def test_fix_pak_beats_the_main_mod(self) -> None:
        # A real MGS Delta mod: its Fix_P loses to its main Outfit_P by name.
        self.assertFalse(outranks_all("Fix_P", ("Outfit_P",)))
        renamed = priority_name("Fix_P", ("Outfit_P",))
        self.assertEqual(renamed, "Fix_1_P")
        self.assertTrue(outranks_all(renamed, ("Outfit_P",)))

    def test_beats_every_rival_by_number_alone(self) -> None:
        rivals = ("zzz_P", "Other_5_P", "Plain")
        renamed = priority_name("Mod_3_P", rivals)
        self.assertEqual(renamed, "Mod_6_P")
        for rival in rivals:
            with self.subTest(rival=rival):
                self.assertGreater(load_rank(renamed)[0], load_rank(rival)[0])

    def test_plain_container_becomes_a_patch(self) -> None:
        self.assertEqual(priority_name("Mod", ("Zed",)), "Mod_1_P")

    def test_needs_a_rival(self) -> None:
        with self.assertRaisesRegex(ValueError, "competitors=\\[\\]"):
            priority_name("Fix_P", ())


if __name__ == "__main__":
    unittest.main()
