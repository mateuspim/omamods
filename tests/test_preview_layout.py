"""Keep real artwork proportional and contained inside the preview split."""

from PIL import Image as PilImage
from textual_image.widget import Image, get_cell_size

from omamods.tui.preview import PicturePreview
from tests.test_tui import TuiFixture


class PreviewLayoutTests(TuiFixture):
    def _assert_contained_ratio(self, preview: PicturePreview, expected: float) -> None:
        picture = preview.query_one(Image)
        cells = get_cell_size()
        pixels_wide = picture.content_size.width * cells.width
        pixels_high = picture.content_size.height * cells.height
        self.assertAlmostEqual(pixels_wide / pixels_high, expected, delta=0.12)
        self.assertLessEqual(picture.region.width, preview.content_size.width)
        self.assertLessEqual(picture.region.height, preview.content_size.height)

    async def test_landscape_and_portrait_artwork_keep_their_aspect_ratio(self) -> None:
        app = self._app({})
        async with app.run_test(size=(160, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            app.run_command_line("game sb")
            await pilot.pause()
            preview = app.screen.query_one(PicturePreview)
            for width, height in ((1600, 900), (600, 1200)):
                path = self.root / f"art-{width}.png"
                PilImage.new("RGB", (width, height), "purple").save(path)
                preview.show(path)
                await pilot.pause()
                self._assert_contained_ratio(preview, width / height)

    async def test_blurred_artwork_stays_proportional_after_resizing(self) -> None:
        path = self.root / "landscape.png"
        PilImage.new("RGB", (1600, 900), "purple").save(path)
        app = self._app({})
        async with app.run_test(size=(160, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            app.run_command_line("game sb")
            await pilot.pause()
            preview = app.screen.query_one(PicturePreview)
            preview.show(path, blurred=True)
            await pilot.pause()
            self._assert_contained_ratio(preview, 1600 / 900)
            await pilot.resize_terminal(120, 36)
            self._assert_contained_ratio(preview, 1600 / 900)
