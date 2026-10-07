"""Pair alternative variants and list archives an install would skip."""

import unittest

from omamods.variant_choices import exclusive_variants, nested_archives

COLOURS = ("Mod/hero/black", "Mod/hero/red", "Mod/knight/black")
MEMBERS = (
    "Mod/hero/black/",
    "Mod/hero/black/Hero_P.pak",
    "Mod/hero/red/Hero_P.pak",
    "Mod/knight/black/Knight_P.pak",
    "Mod/Patch.ZIP",
)


class ExclusiveVariantsTest(unittest.TestCase):
    def test_variants_sharing_a_file_name_exclude_each_other(self) -> None:
        self.assertEqual(
            exclusive_variants(MEMBERS, COLOURS),
            {
                "Mod/hero/black": frozenset({"Mod/hero/red"}),
                "Mod/hero/red": frozenset({"Mod/hero/black"}),
                "Mod/knight/black": frozenset(),
            },
        )

    def test_names_compare_without_case(self) -> None:
        members = ("A/x.PAK", "B/X.pak")
        self.assertEqual(exclusive_variants(members, ("A", "B"))["A"], frozenset({"B"}))

    def test_a_folder_name_prefix_is_not_a_variant(self) -> None:
        members = ("Red/x.pak", "Red2/x.pak")
        self.assertEqual(
            exclusive_variants(members, ("Red", "Red2"))["Red"], frozenset({"Red2"})
        )
        self.assertEqual(exclusive_variants(("Red2/x.pak",), ("Red",))["Red"], set())


class NestedArchivesTest(unittest.TestCase):
    def test_lists_archives_inside_the_archive(self) -> None:
        self.assertEqual(nested_archives(MEMBERS), ("Mod/Patch.ZIP",))


if __name__ == "__main__":
    unittest.main()
