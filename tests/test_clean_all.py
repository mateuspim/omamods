import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from omamods.clean_all import (
    CleanOutcome,
    describe_clean,
    plan_clean,
    protected_folders,
    recorded_mod_ids,
    run_clean,
    summarize_clean,
)
from omamods.pak_games import PAK_SUFFIXES, PakOverlayGame
from omamods.untracked_clean import MANIFEST


def game_at(root: Path) -> PakOverlayGame:
    return PakOverlayGame(
        "g", "G", "g", Path("Paks"), "~mods", (PAK_SUFFIXES,), install_root=root
    )


def install(storage: Path, paks: Path, mod_id: int, relative: str) -> Path:
    """Write a mod file and the record that owns it, as an install would."""
    target = paks / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(f"mod {mod_id}".encode())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    record = storage / "state" / "g" / str(mod_id) / "1.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    asset = {"relative_path": relative, "sha256": digest}
    state = {"paks": str(paks), "file_id": 1, "assets": [asset]}
    record.write_text(json.dumps(state), encoding="utf-8")
    return target


class CleanAllTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.storage, self.game_root = base / "storage", base / "game"
        self.paks = self.game_root / "Paks"
        (self.paks / "base.pak").parent.mkdir(parents=True)
        (self.paks / "base.pak").write_bytes(b"game")
        self.game = game_at(self.game_root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def plan(self, untracked: tuple[Path, ...] = ()):
        games, roots = {"g": self.game}, {"nexus": self.storage}
        return plan_clean(games, {"g": "Game"}, roots, {"g": untracked})

    def test_removes_tracked_and_stray_files_and_keeps_copies(self) -> None:
        tracked = install(self.storage, self.paks, 1, "~mods/A/a.pak")
        stray = self.paks / "~mods/B/b.pak"
        stray.parent.mkdir(parents=True)
        stray.write_bytes(b"stray")
        outcome = run_clean(self.plan((stray,)), self.storage / "removed" / "t")
        self.assertEqual((outcome.uninstalled, outcome.set_aside), (1, 1))
        self.assertFalse((self.paks / "~mods").exists())
        self.assertTrue((self.paks / "base.pak").is_file())
        kept = json.loads((outcome.folder / "tracked" / MANIFEST).read_text("utf-8"))
        self.assertEqual(list(kept.values()), [str(tracked)])
        self.assertEqual(Path(next(iter(kept))).read_bytes(), b"mod 1")

    def test_changed_tracked_file_is_still_removed(self) -> None:
        tracked = install(self.storage, self.paks, 2, "~mods/c.pak")
        tracked.write_bytes(b"edited by hand")
        outcome = run_clean(self.plan(), self.storage / "removed" / "t")
        self.assertEqual((outcome.failures, tracked.exists()), ((), False))
        records = list((self.storage / "state" / "g").rglob("*.json"))
        self.assertEqual(records, [])
        copy = next((outcome.folder / "tracked" / "g").iterdir())
        self.assertEqual(copy.read_bytes(), b"edited by hand")

    def test_game_without_mods_is_left_out_of_the_plan(self) -> None:
        self.assertEqual(self.plan(), ())

    def test_description_lists_files_and_the_way_back(self) -> None:
        install(self.storage, self.paks, 1, "~mods/a.pak")
        text = describe_clean(self.plan())
        self.assertIn("Game: 1 install record(s)", text)
        self.assertIn(str(self.paks / "~mods/a.pak"), text)
        self.assertIn("nothing is deleted", text)


class CleanHelpersTest(unittest.TestCase):
    def test_recorded_mod_ids_reads_folders_and_legacy_records(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            (state / "7").mkdir()
            (state / "3.json").write_text("{}", encoding="utf-8")
            (state / "notes.json").write_text("{}", encoding="utf-8")
            self.assertEqual(recorded_mod_ids(state), (3, 7))

    def test_cyberpunk_keeps_its_shipped_folders(self) -> None:
        root = Path("/games/cp")
        game = PakOverlayGame(
            "c", "C", "c", Path("."), "archive/pc/mod", (), root, redengine=True
        )
        self.assertIn(root / "r6", protected_folders(game))
        self.assertIn(root, protected_folders(game))

    def test_summary_lists_failures(self) -> None:
        outcome = CleanOutcome(Path("/r"), 2, 3, ("G mod 1: broken",), 1)
        text = summarize_clean(outcome)
        self.assertIn("Uninstalled 3 file(s), set aside 2", text)
        self.assertIn("1 failed:\nG mod 1: broken", text)


if __name__ == "__main__":
    unittest.main()
