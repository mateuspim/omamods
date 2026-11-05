import json
from pathlib import Path
import tempfile
import unittest

from omamods.untracked_clean import MANIFEST, describe_found, set_aside


class SetAsideTest(unittest.TestCase):
    def test_moves_files_and_records_their_origin(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            mod = root / "game" / "x.pak"
            mod.parent.mkdir()
            mod.write_bytes(b"data")
            count, folder = set_aside({"g": (mod,)}, root / "removed")
            manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
            self.assertEqual((count, mod.exists()), (1, False))
            self.assertEqual(list(manifest.values()), [str(mod)])
            self.assertTrue(Path(next(iter(manifest))).is_file())

    def test_description_names_games_and_the_way_back(self) -> None:
        text = describe_found({"g": (Path("a.pak"),)}, {"g": "Game"})
        self.assertIn("Game: 1 file(s)", text)
        self.assertIn("not deleted", text)


if __name__ == "__main__":
    unittest.main()
