"""Follow desktop theme changes without touching real Omarchy configuration."""

from dataclasses import replace
from rich.text import Text
from textual.content import Content
from textual.widgets import Static

from omamods.omarchy_palette import OmarchyPalette
from omamods.omarchy_palette import parse_omarchy_palette
from omamods.tui.workspace import WorkspaceStatus
from tests.test_omarchy_palette import LIFELESS_COLOURS, LIGHT_COLOURS, NORD_COLOURS
from tests.test_tui import TuiFixture


class FakePaletteReader:
    """Switch palette snapshots or model an interrupted desktop theme update."""

    def __init__(self, source: str | None) -> None:
        self.source = source
        self.error: Exception | None = None

    def read(self) -> OmarchyPalette | None:
        """Return a test palette; e.g. ``reader.read()``."""
        if self.error is not None:
            raise self.error
        return parse_omarchy_palette(self.source, "Fixture") if self.source else None


class ThemeSyncTests(TuiFixture):
    def _assert_text_colour(self, widget: Static, expected: str) -> None:
        visual = widget.visual
        self.assertIsInstance(visual, Content)
        colour = visual.get_style_at_offset(0).foreground.rich_color
        self.assertEqual(
            colour.get_truecolor(widget.app.ansi_theme).hex.lower(), expected
        )

    async def test_timer_recolours_cached_rich_text_without_reopening_screen(
        self,
    ) -> None:
        app = self._app({})
        palette = FakePaletteReader(NORD_COLOURS)
        app.service.host = replace(app.service.host, palette_reader=palette)
        async with app.run_test() as pilot:
            await self._wait_for_shelf(app, pilot)
            probe = app.screen.query_one("#setup", Static)
            probe.update(Text().append("sync", style="cyan"))
            self._assert_text_colour(probe, "#88c0d0")
            palette.source = LIGHT_COLOURS + '\ncyan = "#115599"'
            await pilot.pause(1.2)
            self._assert_text_colour(probe, "#115599")

    async def test_live_switch_to_community_theme_with_extra_settings(self) -> None:
        app = self._app({})
        palette = FakePaletteReader(NORD_COLOURS)
        app.service.host = replace(app.service.host, palette_reader=palette)
        async with app.run_test() as pilot:
            await self._wait_for_shelf(app, pilot)
            palette.source = LIFELESS_COLOURS
            await pilot.pause(1.2)
            self.assertEqual(app.current_theme.primary, "#abfeff")
            self.assertEqual(app.current_theme.surface, "#243031")
            self.assertEqual(tuple(app.ansi_theme.ansi_colors[6]), (119, 224, 248))

    async def test_theme_switch_preserves_selection(self) -> None:
        app = self._app({})
        palette = FakePaletteReader(NORD_COLOURS)
        app.service.host = replace(app.service.host, palette_reader=palette)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._wait_for_shelf(app, pilot)
            self.assertEqual(app.theme, "omarchy")
            await pilot.press("j")
            selected = app.focused.highlighted
            palette.source = LIGHT_COLOURS
            app.refresh_omarchy_theme()
            await pilot.pause()
            self.assertFalse(app.current_theme.dark)
            self.assertEqual(app.current_theme.primary, "#0055aa")
            self.assertEqual(app.focused.highlighted, selected)
            self.assertEqual(
                app.screen.query_one(WorkspaceStatus).styles.background.hex.lower(),
                app.current_theme.panel.lower(),
            )

    async def test_invalid_or_missing_update_keeps_last_good_theme(self) -> None:
        app = self._app({})
        palette = FakePaletteReader(NORD_COLOURS)
        app.service.host = replace(app.service.host, palette_reader=palette)
        async with app.run_test() as pilot:
            await self._wait_for_shelf(app, pilot)
            original = app.desktop_palette
            palette.source = None
            app.refresh_omarchy_theme()
            self.assertEqual(app.desktop_palette, original)
            palette.source = "broken TOML"
            app.refresh_omarchy_theme()
            palette.error = PermissionError("temporary failure")
            app.refresh_omarchy_theme()
            self.assertEqual(app.desktop_palette, original)

    async def test_absent_omarchy_uses_fallback_and_unchanged_palette_is_quiet(
        self,
    ) -> None:
        app = self._app({})
        async with app.run_test() as pilot:
            await self._wait_for_shelf(app, pilot)
            self.assertEqual(app.theme, "omamods-night")
            palette = FakePaletteReader(NORD_COLOURS)
            app.service.host = replace(app.service.host, palette_reader=palette)
            app.refresh_omarchy_theme()
            original = app.current_theme
            app.refresh_omarchy_theme()
            self.assertIs(app.current_theme, original)
