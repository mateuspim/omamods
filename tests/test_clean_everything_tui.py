import unittest

from omamods.tui.dialogs import ConfirmDialog
from tests.test_tui import TuiFixture


class CleanEverythingTuiTests(TuiFixture):
    async def test_clean_everything_with_no_mods_says_so(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("C")
            messages = [str(n.message) for n in app._notifications]
            self.assertTrue(any("No mods found" in m for m in messages))

    async def test_clean_everything_confirms_then_sets_mods_aside(self) -> None:
        stray = self.root / "SB/SB/Content/Paks/~mods/hand.pak"
        stray.parent.mkdir(parents=True)
        stray.write_bytes(b"mod")
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("C")
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmDialog)
            await pilot.press("y")
            await self._wait_for_shelf(app, pilot)
            self.assertFalse(stray.exists())
            self.assertFalse(stray.parent.exists())
            removed = self.root / "store" / "removed"
            self.assertEqual(len(list(removed.rglob("*hand.pak"))), 1)


if __name__ == "__main__":
    unittest.main()
