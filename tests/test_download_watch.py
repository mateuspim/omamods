"""Notice archives a browser saves into a temporary downloads folder."""

from pathlib import Path
import tempfile
import unittest

from omamods.download_watch import (
    DownloadWatch,
    _copy_across,
    claim_download,
    downloads_folder,
)
from tests.fakes import FakeCommandRunner

HOME = Path("/home/player")


class DownloadsFolderTest(unittest.TestCase):
    def test_uses_the_xdg_download_dir(self) -> None:
        runner = FakeCommandRunner(output="/data/Downloads")
        self.assertEqual(downloads_folder(runner, HOME), Path("/data/Downloads"))
        self.assertEqual(runner.commands, [("xdg-user-dir", "DOWNLOAD")])

    def test_falls_back_to_home_downloads(self) -> None:
        cases = (
            FakeCommandRunner(exit_code=127),
            FakeCommandRunner(output=str(HOME)),
            FakeCommandRunner(output="relative"),
        )
        for runner in cases:
            with self.subTest(output=runner.output, code=runner.exit_code):
                self.assertEqual(downloads_folder(runner, HOME), HOME / "Downloads")


class TemporaryFolder(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def write(self, name: str, size: int = 4) -> Path:
        path = self.folder / name
        path.write_bytes(b"x" * size)
        return path


class DownloadWatchTest(TemporaryFolder):
    def test_ignores_archives_present_at_start(self) -> None:
        self.write("old.zip")
        watch = DownloadWatch.start(self.folder)
        self.assertEqual((watch.poll(), watch.poll()), ((), ()))

    def test_reports_a_new_archive_once_its_size_holds(self) -> None:
        watch = DownloadWatch.start(self.folder)
        self.write("mod.zip", 4)
        self.assertEqual(watch.poll(), ())
        self.write("mod.zip", 8)
        self.assertEqual(watch.poll(), ())
        self.assertEqual(watch.poll(), (self.folder / "mod.zip",))
        self.assertEqual(watch.poll(), ())

    def test_waits_for_chromium_and_firefox_partials(self) -> None:
        watch = DownloadWatch.start(self.folder)
        self.write("a.zip.crdownload")
        self.write("b.7z")
        self.write("b.7z.part")
        self.assertEqual((watch.poll(), watch.poll()), ((), ()))
        (self.folder / "b.7z.part").unlink()
        watch.poll()
        self.assertEqual(watch.poll(), (self.folder / "b.7z",))

    def test_ignores_empty_hidden_and_non_archive_files(self) -> None:
        watch = DownloadWatch.start(self.folder)
        self.write("empty.rar", 0)
        self.write(".com.google.Chrome.x.zip")
        self.write("readme.pdf")
        self.assertEqual((watch.poll(), watch.poll()), ((), ()))

    def test_survives_a_missing_folder(self) -> None:
        watch = DownloadWatch.start(self.folder / "absent")
        self.assertEqual(watch.poll(), ())


class ClaimDownloadTest(TemporaryFolder):
    def test_moves_the_archive_into_staging(self) -> None:
        source = self.write("mod.zip")
        target = claim_download(source, self.folder / "staged" / "1")
        self.assertEqual(target, self.folder / "staged" / "1" / "mod.zip")
        self.assertEqual((source.exists(), target.read_bytes()), (False, b"xxxx"))

    def test_refuses_to_replace_a_staged_file(self) -> None:
        source = self.write("mod.zip")
        staged = self.folder / "staged"
        staged.mkdir()
        (staged / "mod.zip").write_bytes(b"old")
        with self.assertRaisesRegex(ValueError, "expected no file"):
            claim_download(source, staged)
        self.assertTrue(source.exists())

    def test_copies_across_filesystems_before_removing_the_source(self) -> None:
        source = self.write("mod.zip")
        target = self.folder / "mod-copy.zip"
        _copy_across(source, target)
        self.assertEqual((source.exists(), target.read_bytes()), (False, b"xxxx"))
        names = sorted(path.name for path in self.folder.iterdir())
        self.assertEqual(names, ["mod-copy.zip"])


if __name__ == "__main__":
    unittest.main()
