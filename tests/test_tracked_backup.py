import json
from pathlib import Path
import tempfile
import unittest

from omamods.tracked_backup import keep_copies, keep_copy
from omamods.untracked_clean import MANIFEST


class KeepCopiesTest(unittest.TestCase):
    def test_copy_outlives_the_original(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            mod = root / "a.pak"
            mod.write_bytes(b"data")
            keep_copy(mod, root / "kept/a.pak")
            mod.unlink()
            self.assertEqual((root / "kept/a.pak").read_bytes(), b"data")

    def test_manifest_maps_copies_to_original_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            mod = root / "a.pak"
            mod.write_bytes(b"data")
            count = keep_copies({"g": (mod, root / "missing.pak")}, root / "t")
            manifest = json.loads((root / "t" / MANIFEST).read_text("utf-8"))
            self.assertEqual((count, list(manifest.values())), (1, [str(mod)]))

    def test_nothing_to_keep_writes_no_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(keep_copies({"g": ()}, Path(raw) / "t"), 0)
            self.assertFalse((Path(raw) / "t").exists())


if __name__ == "__main__":
    unittest.main()
