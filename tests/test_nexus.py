"""Exercise Nexus selection and safe Cronos overlay behavior offline."""

from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from omamods.cli import run_cli
from omamods.nexus_api import (
    NexusApi,
    NexusFile,
    parse_download_links,
    parse_file_listing,
    parse_nexus_page,
    parse_nxm_link,
    select_file,
)
from omamods.nexus_config import (
    default_config_path,
    initial_config,
    initialize_config,
    parse_user_config,
)
from omamods.nexus_cli import NexusRuntime
from omamods.pak_archive import PlannedAsset, plan_pak_assets
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.pak_storage import (
    InstalledAsset,
    archive_path,
    cache_downloaded_archive,
    download_archive,
    install_pak_archive,
    revert_pak_mod,
)
from omamods.yaml_codec import SafeYamlDecoder
from tests.fakes import (
    FakeArchiveReader,
    FakeConfigFiles,
    FakeFiles,
    FakeNexusTransport,
    app_text,
)

CRONOS = PAK_OVERLAY_GAMES["cronos"]


def plan_cronos_assets(members: tuple[str, ...]) -> tuple[PlannedAsset, ...]:
    return plan_pak_assets(members, CRONOS, None)


def install_cronos_archive(
    archive: Path, paks: Path, record: Path, file_id: int, reader: FakeArchiveReader
) -> tuple[InstalledAsset, ...]:
    planned = plan_cronos_assets(reader.members(archive))
    return install_pak_archive(archive, paks, record, file_id, reader, planned)


class NexusTests(unittest.TestCase):
    def test_cli_config_init_and_download_only(self) -> None:
        manifest = "id: cronos\nname: Cronos\nstatus: discovery\nplatforms: [steam]\nadapter: direct-overlay\nsteam_app_id: 2101960\nnotes: [Test.]"
        files = FakeFiles(
            {
                Path("games/cronos/game.yml"): manifest,
                Path("/steam/steamapps/appmanifest_2101960.acf"): app_text().replace(
                    "42", "2101960"
                ),
            },
            (
                Path("games"),
                Path("games/cronos"),
                Path("/steam"),
                Path("/steam/steamapps"),
            ),
        )
        config_files = FakeConfigFiles()
        transport = FakeNexusTransport()
        runtime = NexusRuntime(
            Path("/home/test"), {}, config_files, transport, FakeArchiveReader({})
        )
        out, err = StringIO(), StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            options = ("--config", str(config))
            self.assertEqual(
                run_cli(
                    (*options, "config", "init"),
                    files,
                    SafeYamlDecoder(),
                    (Path("/steam"),),
                    out,
                    err,
                    runtime,
                ),
                0,
            )
            configured = config_files.contents[config].replace(
                "/home/test/.local/share/omamods", temporary
            )
            config_files.contents[config] = configured.replace(
                'api_key = ""', 'api_key = "secret"'
            )
            self.assertEqual(
                run_cli(
                    (*options, "nexus", "sync", "cronos", "--download-only"),
                    files,
                    SafeYamlDecoder(),
                    (Path("/steam"),),
                    out,
                    err,
                    runtime,
                ),
                0,
            )
            self.assertIn("installed files: 0", out.getvalue())
            self.assertEqual(len(transport.downloads), 1)

    def test_private_config_template_and_paths(self) -> None:
        path = default_config_path(Path("/home/test"), None)
        files = FakeConfigFiles()
        initialize_config(path, Path('/home/test/with "quote"'), files)
        settings = parse_user_config(files.read_text(path), Path("/unused"), "secret")
        self.assertEqual(settings.api_key, "secret")
        self.assertEqual(
            settings.mods[0].url, "https://www.nexusmods.com/cronosthenewdawn/mods/38"
        )
        self.assertEqual(settings.storage_root, Path('/home/test/with "quote"'))
        with self.assertRaises(FileExistsError):
            initialize_config(path, Path("/unused"), files)

    def test_config_rejects_invalid_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "nexus.api_key"):
            parse_user_config("[nexus]\napi_key = 4", Path("/tmp"), None)
        with self.assertRaisesRegex(ValueError, "file_id"):
            parse_user_config(
                "[[mods]]\ngame='cronos'\nurl='x'\nfile_id=-1", Path("/tmp"), None
            )

    def test_null_category_name_falls_back_to_category_id(self) -> None:
        # Regression: RED4ext's deleted file 11722 broke mod 2380's whole listing.
        files = parse_file_listing(
            {
                "files": [
                    {
                        "file_id": 1,
                        "file_name": "a.zip",
                        "category_name": None,
                        "category_id": 6,
                        "uploaded_timestamp": 1,
                    },
                    {"file_id": 2, "file_name": "b.zip", "category_name": "MAIN"},
                ]
            }
        )
        self.assertEqual([f.category for f in files], ["DELETED", "MAIN"])
        # Regression: ArchiveXL's archived file 84351 has an empty file_name.
        broken = {"file_id": 3, "file_name": "", "category_name": "ARCHIVED"}
        self.assertEqual(parse_file_listing({"files": [broken]}), ())
        with self.assertRaisesRegex(ValueError, "expected positive file_id"):
            parse_file_listing({"files": [broken | {"category_name": "MAIN"}]})
        with self.assertRaisesRegex(ValueError, "expected category_name"):
            parse_file_listing(
                {"files": [{"file_id": 1, "file_name": "a.zip", "category_id": 99}]}
            )

    def test_nexus_url_and_file_selection(self) -> None:
        page = parse_nexus_page("https://www.nexusmods.com/cronosthenewdawn/mods/38")
        self.assertEqual((page.domain, page.mod_id), ("cronosthenewdawn", 38))
        files = parse_file_listing(
            {"files": [{"file_id": 7, "file_name": "mod.zip", "category_name": "MAIN"}]}
        )
        self.assertEqual(select_file(files, None).file_id, 7)
        with self.assertRaisesRegex(ValueError, "expected one file"):
            select_file(files, 8)
        with self.assertRaises(ValueError):
            parse_nexus_page("http://www.nexusmods.com/cronosthenewdawn/mods/38")
        with self.assertRaises(ValueError):
            parse_download_links([{"URI": "http://unsafe.test/archive"}])

    def test_nxm_authorization_is_scoped_to_one_file(self) -> None:
        api = NexusApi(FakeNexusTransport(), "secret")
        page = parse_nexus_page("https://www.nexusmods.com/cronosthenewdawn/mods/38")
        file = api.files(page)[0]
        nxm = parse_nxm_link(
            "nxm://cronosthenewdawn/mods/38/files/7?key=abc&expires=9999999999"
        )
        self.assertEqual(
            api.download_url(page, file, nxm), "https://cdn.example/mod.zip"
        )
        with self.assertRaisesRegex(ValueError, "selected Nexus game"):
            api.download_url(
                page,
                file,
                parse_nxm_link(
                    "nxm://other/mods/38/files/7?key=abc&expires=9999999999"
                ),
            )

    def test_archive_plan_rejects_traversal_and_duplicates(self) -> None:
        self.assertEqual(
            plan_cronos_assets(("archive/Mods/a.pak",))[0].target, Path("Mods/a.pak")
        )
        with self.assertRaisesRegex(ValueError, "traversal"):
            plan_cronos_assets(("Mods/../evil.pak",))
        with self.assertRaisesRegex(ValueError, "one archive member"):
            plan_cronos_assets(("Mods/a.pak", "archive/Mods/a.pak"))

    def test_flat_cronos_triplet_targets_mods_folder(self) -> None:
        members = ("sample_P.pak", "sample_P.utoc", "sample_P.ucas")
        planned = plan_cronos_assets(members)
        self.assertEqual(planned[0].target, Path("Mods/sample_P.pak"))
        with self.assertRaisesRegex(ValueError, "same-stem"):
            plan_cronos_assets(("a.pak", "b.utoc", "b.ucas"))

    def test_cache_supplied_archive_refuses_different_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "supplied.zip"
            source.write_bytes(b"first")
            file = NexusFile(0, "supplied.zip", "MAIN", 0)
            cached = cache_downloaded_archive(
                archive_path(root, CRONOS, 38, file), source
            )
            self.assertEqual(cached.read_bytes(), b"first")
            self.assertEqual(
                cache_downloaded_archive(archive_path(root, CRONOS, 38, file), source),
                cached,
            )
            source.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "same cached SHA-256"):
                cache_downloaded_archive(archive_path(root, CRONOS, 38, file), source)

    def test_download_install_and_revert_owned_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paks = root / "game/Cronos/Content/Paks"
            paks.mkdir(parents=True)
            transport = FakeNexusTransport()
            file = NexusFile(7, "mod.zip", "MAIN", 0)
            archive = download_archive(
                archive_path(root, CRONOS, 38, file),
                file,
                "https://cdn.example/mod.zip",
                transport,
            )
            self.assertEqual(len(transport.downloads), 1)
            self.assertEqual(
                download_archive(archive, file, "unused", transport), archive
            )
            reader = FakeArchiveReader({"Mods/a.pak": b"pak", "Mods/a.utoc": b"toc"})
            record = root / "state/cronos/38.json"
            installed = install_cronos_archive(archive, paks, record, 7, reader)
            self.assertEqual(len(installed), 2)
            with self.assertRaisesRegex(ValueError, "revert first"):
                install_cronos_archive(archive, paks, record, 7, reader)
            (paks / "Mods/a.pak").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "file changed"):
                revert_pak_mod(record, CRONOS)
            (paks / "Mods/a.pak").write_bytes(b"pak")
            self.assertEqual(len(revert_pak_mod(record, CRONOS)), 2)
            self.assertFalse((paks / "Mods/a.pak").exists())

    def test_install_never_overwrites_unowned_game_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paks = root / "Paks"
            (paks / "Mods").mkdir(parents=True)
            (paks / "Mods/a.pak").write_bytes(b"user")
            archive = root / "mod.zip"
            archive.write_bytes(b"archive")
            with self.assertRaisesRegex(ValueError, "unowned path"):
                install_cronos_archive(
                    archive,
                    paks,
                    root / "state.json",
                    7,
                    FakeArchiveReader({"Mods/a.pak": b"mod"}),
                )
            self.assertEqual((paks / "Mods/a.pak").read_bytes(), b"user")

    def test_revert_rejects_state_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paks = root / "Paks"
            paks.mkdir()
            (paks / "base.pak").write_bytes(b"game")
            record = root / "state.json"
            record.write_text(
                json.dumps(
                    {
                        "paks": str(paks),
                        "assets": [
                            {"relative_path": "Mods/../base.pak", "sha256": "0" * 64}
                        ],
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "beneath Mods"):
                revert_pak_mod(record, CRONOS)
            self.assertEqual((paks / "base.pak").read_bytes(), b"game")


if __name__ == "__main__":
    unittest.main()
