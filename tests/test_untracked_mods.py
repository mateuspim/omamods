import json
from pathlib import Path
import tempfile
import unittest

from omamods.pak_games import PAK_SUFFIXES, PakOverlayGame
from omamods.untracked_mods import audit_games, owned_paths, untracked_mod_files

GAME = PakOverlayGame("g", "G", "g", Path("Paks"), "Mods", (PAK_SUFFIXES,))


class UntrackedModsTest(unittest.TestCase):
    def test_lists_only_files_without_a_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            mods = root / "Paks" / "Mods"
            mods.mkdir(parents=True)
            (mods / "mine.pak").write_bytes(b"")
            (mods / "hand.pak").write_bytes(b"")
            record = root / "state" / "g" / "1" / "2.json"
            record.parent.mkdir(parents=True)
            state = {
                "paks": str(root / "Paks"),
                "assets": [{"relative_path": "Mods/mine.pak"}],
            }
            record.write_text(json.dumps(state), encoding="utf-8")
            owned = owned_paths(root / "state" / "g")
            found = untracked_mod_files(GAME, root / "Paks", owned)
        self.assertEqual([p.name for p in found], ["hand.pak"])

    def test_missing_state_folder_owns_nothing(self) -> None:
        self.assertEqual(owned_paths(Path("/nonexistent-omamods")), frozenset())

    def test_patch_chain_game_lists_patches_only(self) -> None:
        chain = PakOverlayGame(
            "r",
            "R",
            "r",
            Path("."),
            "",
            (PAK_SUFFIXES,),
            patch_chain="re_chunk_000.pak",
        )
        with tempfile.TemporaryDirectory() as raw:
            paks = Path(raw)
            (paks / "re_chunk_000.pak").write_bytes(b"")
            (paks / "re_chunk_000.pak.patch_009.pak").write_bytes(b"mod data")
            (paks / "re_chunk_000.pak.patch_002.pak").write_bytes(
                b""
            )  # shipped placeholder
            found = untracked_mod_files(chain, paks, frozenset())
        self.assertEqual([p.name for p in found], ["re_chunk_000.pak.patch_009.pak"])

    def test_audit_skips_games_whose_mods_share_the_base_folder(self) -> None:
        mixed = PakOverlayGame("m", "M", "m", Path("Paks"), ".", (PAK_SUFFIXES,))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Paks").mkdir()
            (root / "Paks" / "game_own.pak").write_bytes(b"")
            from dataclasses import replace

            found = audit_games([replace(mixed, install_root=root)], (root,))
        self.assertEqual(found, {})

    def test_audit_reports_by_game_id(self) -> None:
        from dataclasses import replace

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Paks" / "Mods").mkdir(parents=True)
            (root / "Paks" / "Mods" / "x.pak").write_bytes(b"")
            found = audit_games([replace(GAME, install_root=root)], (root,))
        self.assertEqual(list(found), ["g"])


if __name__ == "__main__":
    unittest.main()
