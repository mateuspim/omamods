from pathlib import Path
import tempfile
import unittest

from omamods.empty_folders import prune_empty_parents


class PruneEmptyParentsTest(unittest.TestCase):
    def test_removes_emptied_folders_up_to_a_protected_one(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            gone = root / "Paks/~mods/Pack/a.pak"
            gone.parent.mkdir(parents=True)
            count = prune_empty_parents((gone,), root, frozenset({root / "Paks"}))
            self.assertEqual(count, 2)
            self.assertEqual((root / "Paks").is_dir(), True)
            self.assertEqual((root / "Paks/~mods").exists(), False)

    def test_keeps_a_folder_that_still_holds_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "mods").mkdir()
            (root / "mods/keep.pak").write_bytes(b"")
            count = prune_empty_parents((root / "mods/gone.pak",), root)
            self.assertEqual((count, (root / "mods").is_dir()), (0, True))


if __name__ == "__main__":
    unittest.main()
