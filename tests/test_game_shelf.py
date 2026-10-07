"""Group catalog and installed games into home-screen sections and render them."""

from argparse import Namespace
from io import StringIO
from pathlib import Path
import unittest

from rich.console import Console

from omamods.game_shelf import (
    CATALOG,
    LIBRARY,
    MOD_READY,
    ShelfEntry,
    build_shelf,
)
from omamods.nexus_config import UserSettings
from omamods.nexus_games import NexusGameDirectory
from omamods.pak_games import PakGameCatalog
from omamods.shelf_scan import ShelfSources, scan_shelf
from omamods.host_cli import HostShelfScanner
from omamods.installed_games import InstalledGame, InstalledScan
from omamods.manifests import GameManifest
from omamods.nexus_cli import CatalogSources, NexusRuntime
from omamods.yaml_codec import SafeYamlDecoder
from omamods.tui.shelf_view import (
    entry_detail,
    entry_prompt,
    format_size,
    setup_summary,
    shelf_options,
)
from tests.fakes import (
    FakeArchiveReader,
    FakeConfigFiles,
    FakeFiles,
    FakeNexusTransport,
)

STEAM = Path("/steam")


def manifest(
    game_id: str, app_id: int | None, notes: tuple[str, ...] = ()
) -> GameManifest:
    name = game_id.replace("-", " ").title()
    return GameManifest(
        game_id, name, "discovery", ("steam",), "direct-overlay", notes, app_id
    )


def steam(app_id: str, name: str, ready: bool = True) -> InstalledGame:
    return InstalledGame(
        "Steam", app_id, name, Path(f"/g/{name}"), ready, 3 * 10**9, STEAM
    )


CATALOG_GAMES = (
    manifest("stellar-blade", 30),
    manifest("cronos", 20),
    manifest("dawnwalker", 40, ("Needs a loader.",)),
    manifest("silent-hill", None),
)
FOUND = InstalledScan(
    (
        steam("30", "Stellar Blade™"),
        steam("99", "Zelda-like"),
        steam("40", "The Blood", ready=False),
        InstalledGame("GOG", "30", "Alpha", Path("/g/Alpha"), True),
    ),
    ("a warning",),
)


def render(renderable: object) -> str:
    console = Console(width=100, record=True, color_system=None, file=StringIO())
    console.print(renderable)
    return console.export_text()


class BuildShelfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shelf = build_shelf(CATALOG_GAMES, PakGameCatalog(), FOUND, (STEAM,))

    def test_sections_put_installed_games_first(self) -> None:
        keys = [entry.key for entry in self.shelf.entries]
        self.assertEqual(
            keys,
            [
                "stellar-blade",
                "cronos",
                "dawnwalker",
                "silent-hill",
                "gog:30",
                "steam:99",
            ],
        )
        self.assertEqual(
            [e.section for e in self.shelf.entries],
            [MOD_READY, MOD_READY, CATALOG, CATALOG, LIBRARY, LIBRARY],
        )

    def test_catalog_matches_steam_ids_not_other_stores(self) -> None:
        blade = self.shelf.entries[0]
        self.assertEqual([g.store for g in blade.installs], ["Steam"])
        self.assertEqual(self.shelf.section(LIBRARY)[0].name, "Alpha")
        self.assertEqual(self.shelf.warnings, ("a warning",))

    def test_install_prefers_a_ready_copy(self) -> None:
        broken, ready = steam("1", "A", ready=False), steam("1", "B")
        entry = ShelfEntry("a", "A", LIBRARY, (broken, ready))
        self.assertIs(entry.install, ready)
        self.assertIsNone(ShelfEntry("b", "B", CATALOG, ()).install)


class ScanShelfTests(unittest.TestCase):
    def test_reads_steam_libraries_and_catalog(self) -> None:
        acf = '"AppState"\n{\n"appid" "20"\n"name" "Cronos"\n"installdir" "C"\n"StateFlags" "4"\n}\n'
        files = FakeFiles(
            {STEAM / "steamapps/appmanifest_20.acf": acf},
            (STEAM, STEAM / "steamapps", STEAM / "steamapps/common/C"),
        )
        sources = ShelfSources(
            lambda: CATALOG_GAMES,
            (STEAM,),
            (),
            files,
            PakGameCatalog(),
            lambda: NexusGameDirectory({}),
        )
        shelf = scan_shelf(sources)
        cronos = next(e for e in shelf.entries if e.key == "cronos")
        self.assertTrue(cronos.install.ready)
        self.assertEqual(shelf.libraries, (STEAM,))

    def test_host_scanner_uses_steam_root_override(self) -> None:
        yml = "id: cronos\nname: Cronos\nstatus: discovery\nplatforms: [steam]\nadapter: direct-overlay\nsteam_app_id: 20\n"
        directories = (Path("games"), STEAM, STEAM / "steamapps")
        files = FakeFiles({Path("games/cronos/game.yml"): yml}, directories)
        args = Namespace(games_dir=Path("games"), steam_root=[STEAM])
        sources = CatalogSources(files, SafeYamlDecoder(), ())
        runtime = NexusRuntime(
            Path("/home/me"),
            {},
            FakeConfigFiles(),
            FakeNexusTransport(),
            FakeArchiveReader({}),
        )
        settings = UserSettings("", Path("/store"), {}, ())
        shelf = HostShelfScanner(args, sources, runtime)(settings)
        self.assertEqual([e.key for e in shelf.entries], ["cronos"])
        self.assertEqual(shelf.libraries, (STEAM,))
        self.assertIn(STEAM / "steamapps/libraryfolders.vdf", files.reads)


class ShelfViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shelf = build_shelf(CATALOG_GAMES, PakGameCatalog(), FOUND, (STEAM,))

    def test_format_size(self) -> None:
        self.assertEqual(format_size(52_300_000_000), "52.3 GB")
        self.assertEqual(format_size(340_000_000), "340 MB")
        self.assertEqual(format_size(None), "unknown")

    def test_prompt_shows_mark_name_and_store(self) -> None:
        entries = {e.key: e for e in self.shelf.entries}
        row = render(entry_prompt(entries["stellar-blade"])).rstrip("\n")
        self.assertTrue(row.startswith(" ● Stellar Blade"))
        self.assertTrue(row.endswith("Steam"))
        self.assertEqual(len(row), 100)
        self.assertIn(" ◐ ", render(entry_prompt(entries["dawnwalker"])))
        self.assertIn("not installed", render(entry_prompt(entries["silent-hill"])))

    def test_long_names_stay_on_one_line(self) -> None:
        long_game = steam("7", "METAL GEAR SOLID 2: Sons of Liberty - " * 4)
        entry = ShelfEntry("steam:7", long_game.name, LIBRARY, (long_game,))
        self.assertEqual(render(entry_prompt(entry)).count("\n"), 1)

    def test_options_have_disabled_headings(self) -> None:
        options = shelf_options(self.shelf)
        headings = [o for o in options if o.disabled]
        self.assertEqual(len(headings), 3)
        self.assertEqual(options[0].id, f"section:{MOD_READY}")
        self.assertIn("MOD-READY · 2", str(options[0].prompt))

    def test_detail_card_lists_folder_and_support(self) -> None:
        text = render(entry_detail(self.shelf.entries[0], 3))
        self.assertIn("/g/Stellar Blade™", text)
        self.assertIn("3.0 GB", text)
        self.assertIn("3 mod(s) staged", text)
        catalog = render(entry_detail(self.shelf.entries[2], None))
        self.assertIn("Incomplete or updating", catalog)
        self.assertIn("• Needs a loader.", catalog)
        missing = render(entry_detail(self.shelf.entries[3], None))
        self.assertIn("Not installed", missing)

    def test_setup_summary_reports_scan_state(self) -> None:
        self.assertIn("Scanning", setup_summary(None, False).plain)
        summary = setup_summary(self.shelf, True).plain
        self.assertIn("✔ Nexus API key", summary)
        self.assertIn("✔ 1 Steam libraries · 4 games installed", summary)
        self.assertIn("1 warning(s)", summary)


if __name__ == "__main__":
    unittest.main()
