"""Rename an installed container's files together, and still revert cleanly."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from omamods.container_rename import (
    container_moves,
    rename_container,
    require_unreal_paks,
)
from omamods.install_records import file_state_path
from omamods.installed_containers import recorded_stems
from omamods.load_order_store import load_order_path, write_load_order
from omamods.nexus_config import UserSettings
from omamods.nexus_workflow import (
    LocalArchiveRequest,
    install_local_archive,
    revert_mod_files,
)
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.pak_storage import file_sha256, owned_target, read_ownership
from tests.fakes import FakeArchiveReader

GAME = PAK_OVERLAY_GAMES["stellar-blade"]
FIX_MEMBERS = {f"Fix_P.{suffix}": suffix.encode() for suffix in ("pak", "utoc", "ucas")}
OLD, NEW = "~mods/Fix_P", "~mods/Fix_1_P"


class FailingMove:
    """Rename like os.rename, but fail on the call numbered ``fail_on``."""

    def __init__(self, fail_on: int) -> None:
        self.fail_on = fail_on
        self.calls = 0

    def __call__(self, old: Path, new: Path) -> None:
        self.calls += 1
        if self.calls == self.fail_on:
            raise OSError(f"rename {str(old)!r}: simulated failure")
        old.rename(new)


class ContainerRenameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.paks = base / "SB/Content/Paks"
        self.paks.mkdir(parents=True)
        self.settings = UserSettings("", base / "store", {}, ())
        self.source = base / "Fix.zip"
        self.source.write_bytes(b"zip")
        root = self.settings.storage_root
        self.record = file_state_path(root, GAME, 1, 7, None)

    def _install(self) -> int:
        request = LocalArchiveRequest(self.source, 1, 7, None)
        reader = FakeArchiveReader(dict(FIX_MEMBERS))
        return install_local_archive(GAME, self.settings, self.paks, request, reader)[1]

    def _names(self) -> list[str]:
        return sorted(path.name for path in (self.paks / "~mods").iterdir())

    def test_rename_then_revert_leaves_paks_clean(self) -> None:
        self._install()
        before = json.loads(self.record.read_text())
        moves = rename_container(self.record, GAME, OLD, NEW)
        self.assertEqual(len(moves), 3)
        self.assertEqual(self._names(), ["Fix_1_P.pak", "Fix_1_P.ucas", "Fix_1_P.utoc"])
        after = json.loads(self.record.read_text())
        self.assertEqual(after["archive_sha256"], before["archive_sha256"])
        digests = [asset["sha256"] for asset in after["assets"]]
        self.assertEqual(digests, [asset["sha256"] for asset in before["assets"]])
        self.assertEqual(recorded_stems(self.record), {"Fix_1_P": frozenset({NEW})})
        self.assertEqual(revert_mod_files(GAME, self.settings.storage_root, 1, 7), 3)
        self.assertEqual(self._names(), [])

    def test_reinstall_keeps_the_chosen_name(self) -> None:
        write_load_order(load_order_path(self.record), {OLD: NEW})
        self._install()
        self.assertEqual(self._names(), ["Fix_1_P.pak", "Fix_1_P.ucas", "Fix_1_P.utoc"])

    def test_refuses_an_existing_target(self) -> None:
        self._install()
        (self.paks / "~mods/Fix_1_P.utoc").write_bytes(b"someone else's")
        with self.assertRaisesRegex(ValueError, "expected no file there"):
            rename_container(self.record, GAME, OLD, NEW)
        self.assertIn("Fix_P.utoc", self._names())

    def test_refuses_a_changed_file(self) -> None:
        self._install()
        (self.paks / "~mods/Fix_P.ucas").write_bytes(b"edited")
        with self.assertRaisesRegex(ValueError, "recorded SHA-256"):
            rename_container(self.record, GAME, OLD, NEW)

    def test_failed_move_puts_every_file_back(self) -> None:
        self._install()
        record_text = self.record.read_text()
        with self.assertRaisesRegex(OSError, "simulated failure"):
            rename_container(self.record, GAME, OLD, NEW, FailingMove(3))
        self.assertEqual(self._names(), ["Fix_P.pak", "Fix_P.ucas", "Fix_P.utoc"])
        self.assertEqual(self.record.read_text(), record_text)

    def test_moves_stay_in_the_same_folder(self) -> None:
        self._install()
        with self.assertRaisesRegex(ValueError, "expected another name"):
            container_moves(self.record, GAME, OLD, "~mods/sub/Fix_1_P")
        with self.assertRaisesRegex(ValueError, "expected files of it"):
            container_moves(self.record, GAME, "~mods/Nope_P", "~mods/Nope_1_P")

    def test_only_unreal_pak_games(self) -> None:
        require_unreal_paks(GAME)
        others = [PAK_OVERLAY_GAMES["cyberpunk-2077"]]
        others += [PAK_OVERLAY_GAMES["metalgearsolidvtpp"]]
        others += [replace(GAME, patch_chain="re_chunk_000.pak")]
        for game in others:
            with self.subTest(game=game.game_id):
                with self.assertRaisesRegex(ValueError, "expected an Unreal game"):
                    require_unreal_paks(game)

    def test_storage_wrappers_read_records_like_revert(self) -> None:
        self._install()
        paks, assets = read_ownership(self.record, GAME)
        self.assertEqual(paks, self.paks.resolve())
        target = owned_target(paks, assets[0].relative_path)
        self.assertEqual(file_sha256(target), assets[0].sha256)
        with self.assertRaisesRegex(ValueError, "beneath Paks"):
            owned_target(paks, "../outside.pak")


if __name__ == "__main__":
    unittest.main()
