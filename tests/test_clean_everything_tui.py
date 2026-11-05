import unittest

from textual.widgets import SelectionList, Static

from omamods.tui.clean_picker import CleanPicker
from tests.test_tui import TuiFixture


class CleanEverythingTuiTests(TuiFixture):
    async def test_clean_everything_with_no_mods_says_so(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("C")
            messages = [str(n.message) for n in app._notifications]
            self.assertTrue(any("No mods found" in m for m in messages))

    async def test_clean_everything_picks_games_then_sets_mods_aside(self) -> None:
        stray = self.root / "SB/SB/Content/Paks/~mods/hand.pak"
        stray.parent.mkdir(parents=True)
        stray.write_bytes(b"mod")
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("C")
            await pilot.pause()
            self.assertIsInstance(app.screen, CleanPicker)
            shown = str(app.screen.query_one("#clean-files", Static).content)
            self.assertIn("SB/Content/Paks/~mods/hand.pak", shown)
            await pilot.press("j", "k")
            await pilot.pause()
            self.assertEqual(app.screen.query_one(SelectionList).highlighted, 0)
            await pilot.press("space", "enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, CleanPicker)
            self.assertTrue(stray.exists())
            await pilot.press("space", "enter")
            await self._wait_for_shelf(app, pilot)
            self.assertFalse(stray.exists())
            removed = self.root / "store" / "removed"
            self.assertEqual(len(list(removed.rglob("*hand.pak"))), 1)

    async def test_escape_leaves_every_game_alone(self) -> None:
        stray = self.root / "SB/SB/Content/Paks/~mods/hand.pak"
        stray.parent.mkdir(parents=True)
        stray.write_bytes(b"mod")
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("C")
            await pilot.pause()
            await pilot.press("escape")
            await app.workers.wait_for_complete()
            self.assertTrue(stray.exists())


if __name__ == "__main__":
    unittest.main()
