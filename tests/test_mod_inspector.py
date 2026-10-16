"""Explain the highlighted file using its actual staged and installed state."""

from dataclasses import replace
import unittest

from textual.pilot import Pilot
from textual.widgets import Static

from omamods.mod_sites import AYAKA_SITE
from omamods.tui.app import OmaModsApp
from omamods.tui.file_table import ModFilesTable
from omamods.tui.mod_detail import ModDetail
from omamods.tui.mod_inspector import mod_overview, selected_file_summary
from omamods.tui.workspace import WorkspaceHints, WorkspaceStatus
from tests.test_file_table import FILES, STAGED
from tests.test_tui import TuiFixture


class InspectorTextTests(unittest.TestCase):
    def test_overview_names_source_and_counts_installed_files(self) -> None:
        mod = replace(STAGED, installed=frozenset({7}), site=AYAKA_SITE)
        self.assertIn("01 installed  /  03 files", mod_overview(mod).plain)
        self.assertIn("AyakaMods", mod_overview(mod).plain)
        self.assertIn("Nexus Mods", mod_overview(STAGED).plain)

    def test_next_action_matches_the_selected_file_state(self) -> None:
        installed = replace(STAGED, installed=frozenset({7}))
        self.assertIn(
            "enter  uninstall", selected_file_summary(installed, FILES[0]).plain
        )
        self.assertIn("enter  install", selected_file_summary(STAGED, FILES[0]).plain)
        self.assertIn("enter  download", selected_file_summary(STAGED, FILES[1]).plain)
        self.assertIn("2.0 MB", selected_file_summary(STAGED, FILES[0]).plain)


class InspectorInteractionTests(TuiFixture):
    async def _open_inspector(self, app: OmaModsApp, pilot: Pilot) -> ModDetail:
        await self._wait_for_shelf(app, pilot)
        app.run_command_line("game sb")
        await pilot.pause()
        inspector = app.screen.query_one(ModDetail)
        inspector.show_mod(STAGED)
        return inspector

    async def test_contextual_keys_describe_the_selected_file_action(self) -> None:
        app = self._app({})
        async with app.run_test(size=(160, 45)) as pilot:
            inspector = await self._open_inspector(app, pilot)
            table = inspector.query_one(ModFilesTable)
            hints = app.screen.query_one(WorkspaceHints)
            table.focus()
            app.screen.query_one(WorkspaceStatus).refresh_state()
            self.assertIn("install", hints.current_hints)
            table.move_cursor(row=1)
            hints.refresh_context(table)
            self.assertIn("enter[/] download", hints.current_hints)
            hints.refresh_context(None)
            self.assertEqual(hints.current_hints, hints.hints)

    async def test_queue_focus_exposes_retry_and_clear_keys(self) -> None:
        app = self._app({})
        async with app.run_test() as pilot:
            await self._wait_for_shelf(app, pilot)
            app.run_command_line("queue")
            await pilot.pause()
            app.screen.query_one(WorkspaceStatus).refresh_state()
            hints = app.screen.query_one(WorkspaceHints)
            self.assertIn("retry", hints.current_hints)
            self.assertIn("clear finished", hints.current_hints)

    async def test_cursor_updates_file_details_and_empty_state(self) -> None:
        app = self._app({})
        async with app.run_test(size=(160, 45)) as pilot:
            inspector = await self._open_inspector(app, pilot)
            field = inspector.query_one("#file-inspector", Static)
            self.assertIn("Main archive", str(field.content))
            inspector.query_one(ModFilesTable).focus()
            await pilot.press("down", "down")
            self.assertIn("Classic palette", str(field.content))
            self.assertIn("enter  download", str(field.content))
            inspector.show_mod(replace(STAGED, files=()))
            self.assertEqual(str(field.content), "No files listed for this mod.")
