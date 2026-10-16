"""Regression coverage for file names, state, and selection in narrow splits."""

from dataclasses import replace
from pathlib import Path
import unittest

from omamods.nexus_api import NexusFile
from omamods.staging import StagedMod
from omamods.tui.file_table import ModFilesTable, file_column_widths
from omamods.tui.mod_rows import file_cells
from tests.test_tui import TuiFixture

FILES = (
    NexusFile(7, "Main.zip", "MAIN", 0, "Main archive", "2.0", 2048),
    NexusFile(8, "Textures.zip", "OPTIONAL", 0, "High resolution textures", "2.0"),
    NexusFile(9, "Classic.zip", "OPTIONAL", 0, "Classic palette", "1.0"),
)
STAGED = StagedMod(1, None, FILES, {7: Path("/staged/Main.zip")}, None, frozenset())


class FileCellTests(unittest.TestCase):
    def test_widths_keep_file_and_state_in_every_layout(self) -> None:
        for width in (30, 45, 67, 68, 100):
            columns = file_column_widths(width)
            self.assertEqual([label for label, _ in columns[:2]], ["State", "File"])
            self.assertLessEqual(sum(size + 2 for _, size in columns), width)
        self.assertEqual(len(file_column_widths(45)), 3)
        self.assertEqual(len(file_column_widths(100)), 6)

    def test_file_cells_name_distinct_states_without_two_blank_columns(self) -> None:
        staged = file_cells(STAGED, FILES[0])
        available = file_cells(STAGED, FILES[1])
        installed = file_cells(replace(STAGED, installed=frozenset({7})), FILES[0])
        self.assertEqual(str(staged[0]), "staged")
        self.assertEqual(str(available[0]), "available")
        self.assertEqual(str(installed[0]), "installed")
        self.assertEqual(
            tuple(str(cell) for cell in staged[1:]),
            ("Main archive", "MAIN", "2.0", "2.0 MB", "7"),
        )

    def test_filename_keeps_literal_markup_and_ellipsizes_when_narrow(self) -> None:
        file = replace(FILES[0], display_name="[Optional] outfit [red]")
        name = file_cells(STAGED, file)[1]
        self.assertEqual(str(name), "[Optional] outfit [red]")
        self.assertEqual(name.overflow, "ellipsis")


class FileTableTests(TuiFixture):
    def _assert_table_cursor(
        self, table: ModFilesTable, row: int, columns: int
    ) -> None:
        self.assertEqual(len(table.columns), columns)
        self.assertEqual(table.cursor_row, row)

    async def test_resizing_keeps_names_state_and_selected_file(self) -> None:
        app = self._app({})
        async with app.run_test(size=(200, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            app.run_command_line("game sb")
            await pilot.pause()
            table = app.screen.query_one(ModFilesTable)
            table.show_mod(STAGED)
            table.move_cursor(row=2)
            self.assertEqual(len(table.columns), 6)
            await pilot.resize_terminal(80, 24)
            self._assert_table_cursor(table, 2, 3)
            self.assertEqual(
                table.get_row_at(0), list(file_cells(STAGED, FILES[0])[:3])
            )
            self.assertLess(table.ordered_columns[1].width + 15, table.region.width)
            await pilot.resize_terminal(200, 45)
            self._assert_table_cursor(table, 2, 6)
            table.show_mod(replace(STAGED, files=FILES[:1]))
            self.assertEqual(table.cursor_row, 0)

    async def test_empty_table_still_has_columns_and_accepts_a_later_mod(self) -> None:
        app = self._app({})
        async with app.run_test(size=(80, 24)) as pilot:
            await self._wait_for_shelf(app, pilot)
            app.run_command_line("game sb")
            await pilot.pause()
            table = app.screen.query_one(ModFilesTable)
            self.assertEqual(table.row_count, 0)
            self.assertEqual(
                [str(c.label) for c in table.ordered_columns], ["State", "File", "Kind"]
            )
            table.show_mod(STAGED)
            self.assertEqual(table.row_count, 3)
            table.show_mod(replace(STAGED, files=()))
            self.assertEqual(table.row_count, 0)
