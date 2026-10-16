"""Exercise responsive splits, workspace chrome, and the searchable action picker."""

import unittest
from dataclasses import replace

from textual.pilot import Pilot
from textual.widgets import DataTable, Input, OptionList

from omamods.tui.action_picker import ActionPicker, matching_actions
from omamods.tui.app import OmaModsApp
from omamods.tui.command_bar import CommandPrompt
from omamods.tui.commands import GLOBAL_COMMANDS
from omamods.tui.downloads_screen import DownloadsScreen
from omamods.tui.mods_commands import MODS_COMMANDS
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.workspace import (
    WorkspaceHeader,
    WorkspaceHints,
    WorkspaceStatus,
    cursor_location,
    interaction_mode,
)
from tests.test_tui import TuiFixture


class ActionMatchingTests(unittest.TestCase):
    def test_matches_words_in_name_and_description(self) -> None:
        commands = GLOBAL_COMMANDS + MODS_COMMANDS
        self.assertEqual(matching_actions(commands, ""), commands)
        self.assertEqual(
            [spec.name for spec in matching_actions(commands, "ARTWORK toggle")],
            ["preview"],
        )
        self.assertEqual(matching_actions(commands, "no such action"), ())


class WorkspaceTests(TuiFixture):
    def _assert_mode(self, status: WorkspaceStatus, expected: str) -> None:
        status.refresh_state()
        self.assertEqual(str(status.query_one(".workspace-mode").render()), expected)
        self.assertEqual(
            status.query_one(".workspace-mode").has_class("editing"),
            expected != "NORMAL",
        )

    async def _open_workspace(self, app: OmaModsApp, pilot: Pilot) -> ModsScreen:
        # Keep hand-staged archives offline even when the fixture has an API key.
        app.service.settings = replace(app.service.settings, api_key="")
        for mod_id in (1, 2):
            archive = self.root / f"store/archives/stellar-blade/{mod_id}/0/Outfit.zip"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"archive")
        await self._wait_for_shelf(app, pilot)
        app.run_command_line("game sb")
        await pilot.pause()
        return app.screen

    async def test_library_chrome_and_cursor_skip_section_headings(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            screen = app.screen
            self.assertEqual(screen.query_one(WorkspaceHeader).context, "Your library")
            self.assertIn("space", str(screen.query_one(".hints-global").render()))
            self.assertEqual(cursor_location(app.focused), "01 / 04")
            await pilot.press("G")
            self.assertEqual(cursor_location(app.focused), "04 / 04")
            self.assertEqual(cursor_location(None), "")
            self.assertEqual(cursor_location(Input()), "")

    async def test_small_terminal_keeps_files_visible_without_artwork(self) -> None:
        app = self._app({})
        async with app.run_test(size=(80, 24)) as pilot:
            screen = await self._open_workspace(app, pilot)
            table = screen.query_one("#files", DataTable)
            self.assertFalse(screen.query_one("#preview-pane").display)
            self.assertGreaterEqual(table.region.height, 6)
            self.assertGreaterEqual(table.region.y, 0)
            self.assertLessEqual(table.region.bottom, 20)
            self.assertEqual(cursor_location(table), "01 / 01")
            await pilot.press("l")
            self.assertEqual(app.focused.id, "files")
            await pilot.press("h")
            self.assertEqual(app.focused.id, "mods")

    async def test_resize_and_preview_toggle_preserve_selection(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            screen = await self._open_workspace(app, pilot)
            await pilot.press("j")
            selected = screen.current
            preview = screen.query_one("#preview-pane")
            self.assertTrue(preview.display)
            await pilot.press("p")
            self.assertFalse(preview.display)
            await pilot.press("p")
            self.assertTrue(preview.display)
            await pilot.press("p")
            await pilot.resize_terminal(80, 24)
            self.assertFalse(preview.display)
            await pilot.press("p")
            self.assertTrue(preview.display)
            await pilot.press("p")
            self.assertEqual(screen.current, selected)

    async def test_unrequested_preview_adapts_to_terminal_size(self) -> None:
        app = self._app({})
        async with app.run_test(size=(80, 24)) as pilot:
            screen = await self._open_workspace(app, pilot)
            await pilot.resize_terminal(140, 45)
            self.assertTrue(screen.query_one("#preview-pane").display)
            await pilot.resize_terminal(140, 24)
            self.assertFalse(screen.query_one("#preview-pane").display)

    async def test_status_tracks_focus_and_search_and_command_modes(self) -> None:
        app = self._app({})
        async with app.run_test(size=(100, 30)) as pilot:
            screen = await self._open_workspace(app, pilot)
            status = screen.query_one(WorkspaceStatus)
            self._assert_mode(status, "NORMAL")
            self.assertEqual(interaction_mode(app.screen, app.focused), "NORMAL")
            self.assertIn("MODS", str(status.query_one(".workspace-position").render()))
            await pilot.press("slash", "1")
            self._assert_mode(status, "SEARCH")
            await pilot.press("escape", "colon")
            self._assert_mode(status, "COMMAND")
            await pilot.press("escape")
            self._assert_mode(status, "NORMAL")

    async def test_picker_runs_action_and_prompts_for_required_argument(self) -> None:
        app = self._app({})
        async with app.run_test(size=(120, 40)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("space")
            self.assertIsInstance(app.screen, ActionPicker)
            self.assertEqual(interaction_mode(app.screen, app.focused), "INSERT")
            app.screen.query_one(Input).value = "game"
            await pilot.pause()
            await pilot.press("enter")
            self.assertIsInstance(app.screen, CommandPrompt)
            self.assertEqual(app.screen.query_one(Input).value, "game ")
            await pilot.press("s", "b", "enter")
            self.assertIsInstance(app.screen, ModsScreen)
            await pilot.press("space")
            app.screen.query_one(Input).value = "preview"
            await pilot.pause()
            await pilot.press("enter")
            self.assertIsInstance(app.screen, ModsScreen)
            self.assertFalse(app.screen.query_one("#preview-pane").display)

    async def test_picker_navigation_no_match_and_cancel(self) -> None:
        app = self._app({})
        async with app.run_test(size=(80, 24)) as pilot:
            await self._wait_for_shelf(app, pilot)
            home = app.screen
            await pilot.press("space")
            rows = app.screen.query_one(OptionList)
            await pilot.press("down")
            self.assertEqual(rows.highlighted, 1)
            await pilot.press("up")
            self.assertEqual(rows.highlighted, 0)
            app.screen.query_one(Input).value = "missing action"
            await pilot.pause()
            await pilot.press("enter")
            self.assertIsInstance(app.screen, ActionPicker)
            self.assertTrue(rows.get_option_at_index(0).disabled)
            await pilot.press("escape")
            self.assertIs(app.screen, home)

    async def test_picker_option_selection_and_downloads_chrome(self) -> None:
        app = self._app({})
        async with app.run_test(size=(100, 30)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("space")
            app.screen.query_one(Input).value = "queue"
            await pilot.pause()
            app.screen.query_one(OptionList).focus()
            await pilot.press("enter")
            self.assertIsInstance(app.screen, DownloadsScreen)
            self.assertEqual(
                app.screen.query_one(WorkspaceHeader).badge, "TRANSFER QUEUE"
            )
            self.assertEqual(
                cursor_location(app.screen.query_one(DataTable)), "00 / 00"
            )
            self.assertIn("retry", app.screen.query_one(WorkspaceHints).hints)
            await pilot.press("escape")
            self.assertNotIsInstance(app.screen, DownloadsScreen)
