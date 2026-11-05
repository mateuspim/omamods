import json
from pathlib import Path
import tempfile
import unittest

from omamods.clean_all import GameClean
from omamods.game_revert import OwnedRecord
from omamods.pak_games import PAK_SUFFIXES, PakOverlayGame
from omamods.tui.clean_picker import (
    INDENT as I,
    folder_lines,
    game_detail,
    game_label,
    mod_count,
)

ROOT = Path("/games/sb")
GAME = PakOverlayGame("sb", "SB", "sb", Path("Paks"), "~mods", (PAK_SUFFIXES,), ROOT)


def recorded(folder: Path, mod_id: int, relative: str) -> OwnedRecord:
    record = folder / f"{mod_id}.json"
    state = {"paks": str(ROOT / "Paks"), "assets": [{"relative_path": relative}]}
    record.write_text(json.dumps(state), encoding="utf-8")
    return OwnedRecord("nexus", mod_id, record)


class CleanPickerTextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        folder = Path(self.temporary.name)
        records = (
            recorded(folder, 1, "~mods/a.pak"),
            recorded(folder, 2, "~mods/b.pak"),
        )
        tracked = (ROOT / "Paks/~mods/a.pak", ROOT / "Paks/~mods/b.pak")
        stray = (ROOT / "Paks/~mods/hand.pak",)
        self.game = GameClean("sb", "Stellar Blade", GAME, records, tracked, stray)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_label_puts_the_file_count_before_the_title(self) -> None:
        self.assertEqual(mod_count(self.game), 2)
        self.assertEqual(game_label(self.game), "   3 files  Stellar Blade")

    def test_detail_names_mods_and_lists_files_under_their_folder(self) -> None:
        text = game_detail(self.game, {("nexus", 1): "Nano Suit"})
        self.assertIn("2 mod(s) from OmaMods · 1 file(s) with no install record", text)
        self.assertIn(f"▸ Nano Suit  [nexus 1]\n{I}Paks/~mods/\n{I}{I}a.pak", text)
        self.assertIn("mod 2  [nexus 2]", text)
        self.assertIn(
            f"No install record (moved aside):\n{I}Paks/~mods/\n{I}{I}hand.pak", text
        )

    def test_folder_lines_name_each_folder_once(self) -> None:
        files = (ROOT / "m/b.pak", ROOT / "m/a.pak", ROOT / "x/c.pak")
        self.assertEqual(
            folder_lines(files, ROOT),
            [f"{I}m/", f"{I}{I}a.pak", f"{I}{I}b.pak", f"{I}x/", f"{I}{I}c.pak"],
        )


if __name__ == "__main__":
    unittest.main()
