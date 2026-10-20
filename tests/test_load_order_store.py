"""Remember and reapply containers the user moved to load last."""

from pathlib import Path
import tempfile
import unittest

from omamods.load_order_store import (
    apply_load_order,
    load_order_path,
    read_load_order,
    remember_choice,
    write_load_order,
)
from omamods.pak_archive import PlannedAsset

FIX = {"~mods/Fix_P": "~mods/Fix_1_P"}


class LoadOrderFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.record = Path(self.temporary.name) / "state/sb/1/7.abc.json"

    def test_choices_sit_beside_the_record_but_are_not_records(self) -> None:
        path = load_order_path(self.record)
        self.assertEqual(path.name, "7.abc.load-order")
        self.assertNotEqual(path.suffix, ".json")

    def test_round_trip_and_empty_removes(self) -> None:
        path = load_order_path(self.record)
        self.assertEqual(read_load_order(path), {})
        write_load_order(path, FIX)
        self.assertEqual(read_load_order(path), FIX)
        write_load_order(path, {})
        self.assertFalse(path.exists())

    def test_rejects_unsafe_or_malformed_choices(self) -> None:
        path = load_order_path(self.record)
        path.parent.mkdir(parents=True)
        for text in ("[]", '{"~mods/A_P": "../A_P"}', '{"A_P": "B_P"}', "{"):
            with self.subTest(text=text):
                path.write_text(text)
                with self.assertRaisesRegex(ValueError, "load order="):
                    read_load_order(path)


class RememberChoiceTests(unittest.TestCase):
    def test_keys_stay_the_archive_names(self) -> None:
        once = remember_choice({}, "~mods/Fix_P", "~mods/Fix_1_P")
        self.assertEqual(once, FIX)
        twice = remember_choice(once, "~mods/Fix_1_P", "~mods/Fix_4_P")
        self.assertEqual(twice, {"~mods/Fix_P": "~mods/Fix_4_P"})

    def test_renaming_back_forgets_the_choice(self) -> None:
        self.assertEqual(remember_choice(FIX, "~mods/Fix_1_P", "~mods/Fix_P"), {})


class ApplyLoadOrderTests(unittest.TestCase):
    def test_renames_every_file_of_the_chosen_container_only(self) -> None:
        planned = (
            PlannedAsset("Fix_P.pak", Path("~mods/Fix_P.pak")),
            PlannedAsset("Fix_P.utoc", Path("~mods/Fix_P.utoc")),
            PlannedAsset("Main_P.pak", Path("~mods/Main_P.pak")),
            PlannedAsset("dll", Path("~mods/Fix_P.pak"), beside_exe=True),
        )
        targets = [a.target.as_posix() for a in apply_load_order(planned, FIX)]
        self.assertEqual(
            targets,
            ["~mods/Fix_1_P.pak", "~mods/Fix_1_P.utoc", "~mods/Main_P.pak"]
            + ["~mods/Fix_P.pak"],
        )


if __name__ == "__main__":
    unittest.main()
