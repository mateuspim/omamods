import unittest

from omamods.tui.dialogs import VariantPicker


class VariantPickerLabelTests(unittest.TestCase):
    def test_non_clashing_folder_is_a_part_and_clashing_is_an_alternative(self) -> None:
        picker = VariantPicker(
            "x",
            ("Main", "Red", "Blue"),
            {"Red": frozenset({"Blue"}), "Blue": frozenset({"Red"})},
        )
        self.assertEqual(picker._label("Main"), "Main  (part of this mod)")
        self.assertEqual(picker._label("Red"), "Red  (alternative)")


if __name__ == "__main__":
    unittest.main()
