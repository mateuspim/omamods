"""Save and apply NSFW hand marks and the hide toggle."""

from pathlib import Path
import tempfile
import unittest

from omamods.adult_marks import (
    ADULT_MARKS_FILE,
    BLUR,
    HIDE,
    SHOW,
    AdultMarks,
    is_adult,
    load_adult_marks,
    next_mode,
    save_adult_marks,
    with_mark,
)
from omamods.nexus_api import NexusModInfo
from omamods.staging import StagedMod
from PIL import Image as PilImage

from omamods.tui.preview import BLUR_WIDTH, blurred_picture
from omamods.tui.mod_rows import describe_mod, mod_prompt, visible_mods


class AdultMarksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_nothing_saved_shows_everything(self) -> None:
        self.assertEqual(load_adult_marks(self.root), AdultMarks())

    def test_marks_and_toggle_survive_a_restart(self) -> None:
        marks = with_mark(AdultMarks(mode=HIDE), "sb", "ayaka:4", True)
        save_adult_marks(self.root, marks)
        self.assertEqual(load_adult_marks(self.root), marks)

    def test_pictures_start_blurred_and_h_cycles_modes(self) -> None:
        self.assertEqual(AdultMarks().mode, BLUR)
        self.assertEqual([next_mode(m) for m in (BLUR, HIDE, SHOW)], [HIDE, SHOW, BLUR])

    def test_files_from_before_blur_keep_their_choice(self) -> None:
        path = self.root / ADULT_MARKS_FILE
        path.write_text('{"hide": true, "marks": {}}', encoding="utf-8")
        self.assertEqual(load_adult_marks(self.root).mode, HIDE)
        path.write_text('{"hide": false, "marks": {}}', encoding="utf-8")
        self.assertEqual(load_adult_marks(self.root).mode, BLUR)

    def test_hand_mark_beats_the_site_flag(self) -> None:
        marks = with_mark(AdultMarks(), "sb", "nexus:1", False)
        self.assertFalse(is_adult(marks, "sb", "nexus:1", flagged=True))
        self.assertTrue(is_adult(marks, "sb", "nexus:2", flagged=True))
        self.assertFalse(is_adult(marks, "cronos", "nexus:9", flagged=False))

    def test_marks_stay_per_game(self) -> None:
        marks = with_mark(
            with_mark(AdultMarks(), "sb", "nexus:1", True), "cp", "nexus:1", False
        )
        self.assertEqual(
            marks.marks, {"sb": {"nexus:1": True}, "cp": {"nexus:1": False}}
        )

    def test_unreadable_file_names_its_path(self) -> None:
        (self.root / ADULT_MARKS_FILE).write_text('{"marks": []}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, ADULT_MARKS_FILE):
            load_adult_marks(self.root)


def staged(mod_id: int, adult: bool = False) -> StagedMod:
    info = NexusModInfo(f"Suit {mod_id}", "", "", "1.0", None, adult)
    return StagedMod(mod_id, info, (), {}, None, frozenset())


class AdultRowTests(unittest.TestCase):
    def test_visible_mods_drop_hidden_keys(self) -> None:
        mods = (staged(1), staged(2))
        shown = visible_mods(mods, "suit", frozenset({"nexus:1"}))
        self.assertEqual([m.mod_id for m in shown], [2])

    def test_adult_rows_and_details_carry_a_badge(self) -> None:
        self.assertIn("18+", str(mod_prompt(staged(1), adult=True).columns[2]._cells))
        self.assertIn("18+ NSFW", describe_mod(staged(1), adult=True))
        self.assertNotIn("NSFW", describe_mod(staged(1)))


class BlurredPictureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_blur_shrinks_and_smooths_the_picture(self) -> None:
        picture = self.root / "p.png"
        sharp = PilImage.new("RGB", (800, 400), "white")
        sharp.paste((0, 0, 0), (0, 0, 400, 400))
        sharp.save(picture)
        blurred = blurred_picture(picture)
        self.assertEqual(blurred.size, (BLUR_WIDTH, BLUR_WIDTH // 2))
        # The hard black/white edge becomes a grey ramp.
        edge = blurred.getpixel((BLUR_WIDTH // 2, BLUR_WIDTH // 4))
        self.assertTrue(40 < edge[0] < 215, edge)

    def test_unreadable_picture_raises(self) -> None:
        broken = self.root / "broken.png"
        broken.write_bytes(b"not a png")
        with self.assertRaises(OSError):
            blurred_picture(broken)


if __name__ == "__main__":
    unittest.main()
