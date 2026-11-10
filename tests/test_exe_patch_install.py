"""Applying and reverting an executable patch with a stored original."""

import json
from pathlib import Path
import tempfile
import unittest

from omamods.exe_byte_patches import sha256_hex
from omamods.exe_patch_install import (
    ExePatchTarget,
    apply_exe_patch,
    describe_patch_state,
    load_patch_record,
    remove_patch_files,
    revert_exe_patch,
)

ORIGINAL, PATCHED = b"original exe", b"patched exe!"


class ExePatchInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        exe = root / "game" / "Game.exe"
        exe.parent.mkdir()
        exe.write_bytes(ORIGINAL)
        self.target = ExePatchTarget.for_game(root / "storage", "demo", exe)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _apply(self) -> None:
        apply_exe_patch(self.target, ORIGINAL, PATCHED, "Demo 3440x1440")

    def test_storage_paths(self) -> None:
        root = Path(self.temp.name) / "storage"
        self.assertEqual(self.target.record, root / "state/demo/exe-patch.json")
        self.assertEqual(self.target.backup, root / "backups/demo/Game.exe.original")

    def test_apply_keeps_the_original_and_records_hashes(self) -> None:
        self._apply()
        self.assertEqual(self.target.exe.read_bytes(), PATCHED)
        self.assertEqual(self.target.backup.read_bytes(), ORIGINAL)
        record = load_patch_record(self.target)
        assert record is not None
        self.assertEqual(record.original_sha256, sha256_hex(ORIGINAL))
        self.assertEqual(record.patched_sha256, sha256_hex(PATCHED))
        self.assertIn("patched (Demo 3440x1440)", describe_patch_state(self.target))

    def test_apply_twice_is_refused(self) -> None:
        self._apply()
        with self.assertRaisesRegex(ValueError, "already patched"):
            self._apply()

    def test_apply_refuses_an_exe_that_changed_meanwhile(self) -> None:
        self.target.exe.write_bytes(b"something else")
        with self.assertRaisesRegex(ValueError, "changed while"):
            self._apply()
        self.assertFalse(self.target.backup.exists())

    def test_stale_backup_is_refused(self) -> None:
        self.target.backup.parent.mkdir(parents=True)
        self.target.backup.write_bytes(b"old")
        with self.assertRaisesRegex(ValueError, "not reverted cleanly"):
            self._apply()
        self.assertEqual(self.target.exe.read_bytes(), ORIGINAL)

    def test_revert_restores_and_clears(self) -> None:
        self._apply()
        self.assertIn("restored", revert_exe_patch(self.target))
        self.assertEqual(self.target.exe.read_bytes(), ORIGINAL)
        self.assertFalse(self.target.backup.exists())
        self.assertIsNone(load_patch_record(self.target))
        self.assertIn("not patched", describe_patch_state(self.target))

    def test_revert_after_steam_restored_the_original(self) -> None:
        self._apply()
        self.target.exe.write_bytes(ORIGINAL)
        self.assertIn("original again", describe_patch_state(self.target))
        self.assertIn("already the original", revert_exe_patch(self.target))
        self.assertIsNone(load_patch_record(self.target))

    def test_revert_refuses_a_changed_exe(self) -> None:
        self._apply()
        self.target.exe.write_bytes(b"updated by Steam")
        self.assertIn("changed since", describe_patch_state(self.target))
        with self.assertRaisesRegex(ValueError, "verify in Steam"):
            revert_exe_patch(self.target)
        self.assertEqual(self.target.backup.read_bytes(), ORIGINAL)

    def test_revert_refuses_a_damaged_backup(self) -> None:
        self._apply()
        self.target.backup.write_bytes(b"damaged")
        with self.assertRaisesRegex(ValueError, "expected sha256"):
            revert_exe_patch(self.target)
        self.assertEqual(self.target.exe.read_bytes(), PATCHED)

    def test_revert_without_a_record(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected an OmaMods patch record"):
            revert_exe_patch(self.target)

    def test_remove_restores_a_patched_exe_and_deletes_storage(self) -> None:
        self._apply()
        self.assertIn("restored", remove_patch_files(self.target))
        self.assertEqual(self.target.exe.read_bytes(), ORIGINAL)
        self.assertFalse(self.target.backup.parent.exists())
        self.assertFalse(self.target.record.parent.exists())

    def test_remove_deletes_a_leftover_backup(self) -> None:
        self.target.backup.parent.mkdir(parents=True)
        self.target.backup.write_bytes(ORIGINAL)
        self.assertIn("leftover backup", remove_patch_files(self.target))
        self.assertFalse(self.target.backup.parent.exists())
        self.assertEqual(self.target.exe.read_bytes(), ORIGINAL)

    def test_remove_with_nothing_stored(self) -> None:
        self.assertIn("nothing stored", remove_patch_files(self.target))

    def test_malformed_record_is_refused(self) -> None:
        self.target.record.parent.mkdir(parents=True)
        self.target.record.write_text(json.dumps({"exe": "x"}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "expected keys"):
            load_patch_record(self.target)


if __name__ == "__main__":
    unittest.main()
