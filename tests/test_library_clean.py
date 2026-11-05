from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from omamods.pak_games import PAK_SUFFIXES, PakOverlayGame
from omamods.tui.library_clean import LibraryClean


@dataclass
class FakeSettings:
    storage_root: Path


class FakeCleanService:
    """Stands in for ModsService: one storage root for every site."""

    def __init__(self, root: Path) -> None:
        self.settings = FakeSettings(root)

    def state_root(self, site: str) -> Path:
        return self.settings.storage_root


class LibraryCleanTest(unittest.TestCase):
    def test_plan_and_run_set_aside_strays_in_a_dated_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            stray = root / "game/Paks/Mods/x.pak"
            stray.parent.mkdir(parents=True)
            stray.write_bytes(b"x")
            cleaner = LibraryClean(FakeCleanService(root))  # type: ignore[arg-type]
            game = PakOverlayGame(
                "g", "G", "g", Path("Paks"), "Mods", (PAK_SUFFIXES,), root / "game"
            )
            cleaner.pak_games = {"g": game}
            cleaner.untracked = {"g": (stray,)}
            outcome = cleaner.run(cleaner.plan())
            self.assertEqual((outcome.set_aside, stray.exists()), (1, False))
            self.assertEqual(outcome.folder.parent, root / "removed")
            self.assertFalse((root / "game/Paks/Mods").exists())

    def test_nothing_found_plans_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cleaner = LibraryClean(FakeCleanService(Path(raw)))  # type: ignore[arg-type]
            self.assertEqual(cleaner.plan(), ())


if __name__ == "__main__":
    unittest.main()
