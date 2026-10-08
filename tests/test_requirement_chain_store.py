"""Save, load, and clear the on-disk requirement chain."""

from pathlib import Path
import tempfile
import unittest

from omamods.nexus_api import NexusFile
from omamods.requirement_chain import ChainStep
from omamods.requirement_chain_store import (
    SavedChain,
    chain_record_path,
    clear_chain,
    load_chain,
    save_chain,
)

STEPS = (
    ChainStep(2380, "RED4ext", (NexusFile(1, "r.zip", "MAIN", 5, "RED4ext", "1.30"),)),
    ChainStep(100, "Third Person", (NexusFile(3, "t.zip", "MAIN", 6),), True),
)


class ChainStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = chain_record_path(Path(self.temp.name))

    def test_round_trip(self) -> None:
        save_chain(self.path, SavedChain("cyberpunk-2077", STEPS))
        self.assertEqual(load_chain(self.path), SavedChain("cyberpunk-2077", STEPS))

    def test_missing_record_is_no_chain(self) -> None:
        self.assertIsNone(load_chain(self.path))

    def test_clear_removes_the_record(self) -> None:
        save_chain(self.path, SavedChain("cyberpunk-2077", STEPS))
        clear_chain(self.path)
        clear_chain(self.path)
        self.assertIsNone(load_chain(self.path))

    def test_bad_records_name_the_path(self) -> None:
        self.path.parent.mkdir(parents=True)
        for body in ("{", '{"game_id": "g", "steps": []}', '{"steps": [1]}'):
            with self.subTest(body=body):
                self.path.write_text(body)
                with self.assertRaisesRegex(ValueError, "requirement chain="):
                    load_chain(self.path)

    def test_last_step_must_be_the_target(self) -> None:
        save_chain(self.path, SavedChain("g", STEPS[:1]))
        with self.assertRaisesRegex(ValueError, "ending with the target"):
            load_chain(self.path)


if __name__ == "__main__":
    unittest.main()
