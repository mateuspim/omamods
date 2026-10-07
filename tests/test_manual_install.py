"""Exercise installing hand-downloaded archives without a Nexus API key."""

from io import StringIO
from pathlib import Path
import tempfile
import unittest

from omamods.cli import run_cli
from omamods.nexus_cli import NexusRuntime
from omamods.nexus_config import parse_user_config
from omamods.yaml_codec import SafeYamlDecoder
from tests.fakes import (
    FakeArchiveReader,
    FakeConfigFiles,
    FakeFiles,
    FakeNexusTransport,
)

STELLAR_BLADE_MANIFEST = (
    "id: stellar-blade\nname: Stellar Blade\nstatus: discovery\n"
    "platforms: [steam]\nadapter: direct-overlay\nsteam_app_id: 3489700\n"
    "notes: [Test.]"
)


class FakeStellarBladeCatalog(FakeFiles):
    """Provide the Stellar Blade manifest and an empty Steam library."""

    def __init__(self) -> None:
        super().__init__(
            {Path("games/stellar-blade/game.yml"): STELLAR_BLADE_MANIFEST},
            (Path("games"), Path("/steam"), Path("/steam/steamapps")),
        )


class ManualInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paks = self.root / "StellarBlade/SB/Content/Paks"
        self.paks.mkdir(parents=True)
        self.archive = self.root / "Downloads/Suit-1-1-0-123.zip"
        self.archive.parent.mkdir()
        self.archive.write_bytes(b"zip")
        self.config_files = FakeConfigFiles()
        self.transport = FakeNexusTransport()
        self.out, self.err = StringIO(), StringIO()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, reader: FakeArchiveReader, *argv: str) -> int:
        runtime = NexusRuntime(self.root, {}, self.config_files, self.transport, reader)
        options = ("--config", str(self.root / "config.toml"))
        return run_cli(
            (*options, *argv),
            FakeStellarBladeCatalog(),
            SafeYamlDecoder(),
            (Path("/steam"),),
            self.out,
            self.err,
            runtime,
        )

    def _configure_install_dir(self) -> None:
        self.config_files.contents[self.root / "config.toml"] = (
            f'[storage]\nroot = "{self.root / "store"}"\n\n'
            f'[games.stellar-blade]\ninstall_dir = "{self.root / "StellarBlade"}"\n'
        )

    def test_install_and_revert_without_api_key(self) -> None:
        self._configure_install_dir()
        reader = FakeArchiveReader({"Black/s.pak": b"pak", "White/s.pak": b"w"})
        argv = ("nexus", "install", "stellar-blade", "1", str(self.archive))
        self.assertEqual(self._run(reader, *argv, "--option", "Black"), 0)
        self.assertEqual((self.paks / "~mods/Black/s.pak").read_bytes(), b"pak")
        self.assertFalse((self.paks / "~mods/White").exists())
        cached = self.root / "store/archives/stellar-blade/1/0/Suit-1-1-0-123.zip"
        self.assertTrue(cached.is_file())
        self.assertEqual(self.transport.requests, [])
        self.assertEqual(self._run(reader, "nexus", "revert", "stellar-blade", "1"), 0)
        self.assertFalse((self.paks / "~mods/Black/s.pak").exists())

    def test_install_reports_missing_archive(self) -> None:
        self._configure_install_dir()
        argv = ("nexus", "install", "stellar-blade", "1", str(self.root / "gone.zip"))
        self.assertEqual(self._run(FakeArchiveReader({}), *argv), 2)
        self.assertIn("expected an existing downloaded file", self.err.getvalue())

    def test_revert_works_without_config_file(self) -> None:
        self.assertEqual(
            self._run(FakeArchiveReader({}), "nexus", "revert", "stellar-blade", "9"),
            2,
        )
        self.assertIn("state/stellar-blade/9.json", self.err.getvalue())

    def test_sync_without_api_key_points_to_manual_install(self) -> None:
        self.config_files.contents[self.root / "config.toml"] = ""
        argv = ("nexus", "sync", "stellar-blade", "--download-only")
        self.assertEqual(self._run(FakeArchiveReader({}), *argv), 2)
        self.assertIn("omamods nexus install", self.err.getvalue())

    def test_sync_rejects_page_from_another_game(self) -> None:
        self.config_files.contents[self.root / "config.toml"] = (
            '[nexus]\napi_key = "secret"\n[[mods]]\ngame = "stellar-blade"\n'
            'url = "https://www.nexusmods.com/cronosthenewdawn/mods/38"\n'
        )
        argv = ("nexus", "sync", "stellar-blade", "--download-only")
        self.assertEqual(self._run(FakeArchiveReader({}), *argv), 2)
        self.assertIn("expected 'stellarblade'", self.err.getvalue())


class MultiGameConfigTests(unittest.TestCase):
    def test_stellar_blade_mod_with_option_and_install_dir(self) -> None:
        settings = parse_user_config(
            '[games.stellar-blade]\ninstall_dir = "/games/SB"\n\n'
            '[[mods]]\ngame = "stellar-blade"\n'
            'url = "https://www.nexusmods.com/stellarblade/mods/1"\noption = "Black"',
            Path("/data"),
            None,
        )
        self.assertEqual(settings.install_dirs, {"stellar-blade": Path("/games/SB")})
        self.assertEqual(settings.mods[0].option, "Black")

    def test_rejects_unsupported_games_and_empty_option(self) -> None:
        with self.assertRaisesRegex(ValueError, "games tables=\\['dawnwalker'\\]"):
            parse_user_config("[games.dawnwalker]\n", Path("/data"), None)
        with self.assertRaisesRegex(ValueError, "expected game in"):
            parse_user_config("[[mods]]\ngame='dawnwalker'\nurl='x'", Path("/d"), None)
        with self.assertRaisesRegex(ValueError, "option=' '"):
            parse_user_config(
                "[[mods]]\ngame='cronos'\nurl='x'\noption=' '", Path("/d"), None
            )


if __name__ == "__main__":
    unittest.main()
