"""Revert every install record of a game in a safe order, past failures."""

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest

from omamods.game_revert import (
    GameRevert,
    OwnedRecord,
    RecordRevert,
    highest_patch,
    revert_game_records,
    revert_order,
)
from omamods.install_records import mod_state_records
from omamods.nexus_config import UserSettings
from omamods.nexus_workflow import (
    LocalArchiveRequest,
    install_local_archive,
    revert_mod_files,
)
from omamods.pak_archive import PlannedAsset
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.pak_storage import install_pak_archive
from omamods.re_engine_layout import BASE_PAK
from omamods.re_patch_chain import patch_name
from tests.fakes import FakeArchiveReader
from tests.test_re_engine import V4_HEADER, re7_game

MGS_DELTA = PAK_OVERLAY_GAMES["metalgearsoliddeltasnakeeater"]


def _write_record(path: Path, relative_paths: tuple[str, ...]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    assets = [{"relative_path": name, "sha256": "0" * 64} for name in relative_paths]
    path.write_text(json.dumps({"paks": "/g", "assets": assets}))
    return path


class PatchChainRevertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.game_root = base / "RE7"
        self.game_root.mkdir()
        (self.game_root / BASE_PAK).write_bytes(V4_HEADER)
        # Capcom's 0-byte patch_002, as RE7 ships it.
        self._patch(2).write_bytes(b"")
        self.root = base / "storage"
        self.game = replace(re7_game(), install_root=self.game_root)
        self.source = base / "mod.zip"
        self.source.write_bytes(b"zip")

    def _patch(self, number: int) -> Path:
        return self.game_root / patch_name(BASE_PAK, number)

    def _install(self, mod_id: int, contents: bytes) -> None:
        reader = FakeArchiveReader({"Mod/a.pak": contents})
        request = LocalArchiveRequest(self.source, mod_id, 1, None)
        settings = UserSettings("", self.root, {}, ())
        install_local_archive(self.game, settings, self.game_root, request, reader)

    def _owned(self, *mod_ids: int) -> tuple[OwnedRecord, ...]:
        return tuple(
            OwnedRecord("nexus", mod_id, record)
            for mod_id in mod_ids
            for record in mod_state_records(self.root, self.game, mod_id)
        )

    def test_one_mod_at_a_time_from_the_bottom_strands_a_placeholder(self) -> None:
        # Why order matters: the lower mod leaves a placeholder for the upper.
        self._install(5, b"one")
        self._install(6, b"two")
        revert_mod_files(self.game, self.root, 5, None)
        revert_mod_files(self.game, self.root, 6, None)
        self.assertEqual(self._patch(1).read_bytes(), V4_HEADER)

    def test_reverting_all_restores_the_shipped_chain(self) -> None:
        self._install(5, b"one")
        self._install(6, b"two")
        outcome = revert_game_records(self.game, self._owned(5, 6))
        self.assertFalse(self._patch(1).exists())
        self.assertEqual(self._patch(2).read_bytes(), b"")
        self.assertEqual(outcome.removed_files(), 2)
        self.assertEqual(outcome.failures(), ())

    def test_changed_patch_fails_alone_and_keeps_the_chain(self) -> None:
        self._install(5, b"one")
        self._install(6, b"two")
        self._patch(2).write_bytes(b"game update")
        outcome = revert_game_records(self.game, self._owned(5, 6))
        self.assertEqual(outcome.cleared_mods(), frozenset({("nexus", 5)}))
        (failure,) = outcome.failures()
        self.assertEqual((failure.mod_id, failure.file_id), (6, 1))
        self.assertIn("file changed", failure.error)
        # Patch 002 still loads, so the emptied 001 must not cut the chain.
        self.assertEqual(self._patch(1).read_bytes(), V4_HEADER)

    def test_highest_patch_reads_the_record(self) -> None:
        names = (patch_name(BASE_PAK, 3), patch_name(BASE_PAK, 12))
        record = _write_record(self.root / "r.json", names)
        self.assertEqual(highest_patch(record, BASE_PAK), 12)
        self.assertEqual(highest_patch(record, None), 0)

    def test_unreadable_record_has_no_patch(self) -> None:
        record = self.root / "broken.json"
        record.parent.mkdir(parents=True)
        record.write_text("{")
        self.assertEqual(highest_patch(record, BASE_PAK), 0)
        self.assertEqual(highest_patch(self.root / "missing.json", BASE_PAK), 0)


class RevertOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _owned(self, name: str, patch: int, installed_at: int) -> OwnedRecord:
        record = _write_record(self.root / name, (patch_name(BASE_PAK, patch),))
        os.utime(record, ns=(installed_at, installed_at))
        return OwnedRecord("nexus", patch, record)

    def test_patch_chain_reverts_the_highest_patch_first(self) -> None:
        low = self._owned("low.json", 1, 9_000)
        high = self._owned("high.json", 4, 1_000)
        self.assertEqual(revert_order((low, high), BASE_PAK), (high, low))

    def test_other_games_revert_the_newest_install_first(self) -> None:
        old = self._owned("old.json", 4, 1_000)
        new = self._owned("new.json", 1, 9_000)
        self.assertEqual(revert_order((old, new), None), (new, old))


class StackedConfigRevertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.config = base / "pfx/Saved/Config/Windows"
        self.config.mkdir(parents=True)
        self.engine_ini = self.config / "Engine.ini"
        self.engine_ini.write_bytes(b"[game]")
        self.state = base / "state"
        self.archive = base / "mod.zip"
        self.archive.write_bytes(b"zip")

    def _install(self, mod_id: int, contents: bytes, installed_at: int) -> OwnedRecord:
        record = self.state / str(mod_id) / "1.config.json"
        reader = FakeArchiveReader({"Engine.ini": contents})
        planned = (
            PlannedAsset(
                "Engine.ini", Path("Engine.ini"), user_editable=True, user_config=True
            ),
        )
        install_pak_archive(self.archive, self.config, record, 1, reader, planned)
        os.utime(record, ns=(installed_at, installed_at))
        return OwnedRecord("nexus", mod_id, record)

    def test_stacked_engine_ini_brings_the_games_file_back(self) -> None:
        first = self._install(1, b"[first]", 1_000)
        second = self._install(2, b"[second]", 2_000)
        outcome = revert_game_records(MGS_DELTA, (first, second))
        self.assertEqual(self.engine_ini.read_bytes(), b"[game]")
        self.assertEqual(outcome.removed_files(), 2)
        self.assertEqual(list(self.state.rglob("*.originals")), [])


class GameRevertTests(unittest.TestCase):
    def test_outcome_counts_files_mods_and_failures(self) -> None:
        failed = RecordRevert("ayaka", 2, 9, 0, "owned SHA-256='x': expected hex")
        outcome = GameRevert(
            (RecordRevert("nexus", 1, 7, 3), RecordRevert("nexus", 1, 8, 2), failed)
        )
        self.assertEqual(outcome.removed_files(), 5)
        self.assertEqual(outcome.cleared_mods(), frozenset({("nexus", 1)}))
        self.assertEqual(outcome.failures(), (failed,))

    def test_unreadable_record_is_reported_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            record = Path(folder) / "state/sb/3.json"
            record.parent.mkdir(parents=True)
            record.write_text("{")
            game = PAK_OVERLAY_GAMES["stellar-blade"]
            outcome = revert_game_records(game, (OwnedRecord("nexus", 3, record),))
        (failure,) = outcome.failures()
        self.assertIsNone(failure.file_id)
        self.assertIn("expected a valid ownership record", failure.error)


if __name__ == "__main__":
    unittest.main()
