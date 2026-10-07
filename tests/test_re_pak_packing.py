"""Pack Fluffy-format natives/ mods into RE Engine patch paks."""

from dataclasses import replace
from io import BytesIO
from pathlib import Path
import struct
import tempfile
import unittest

from omamods.mod_plan import FilePlan, describe_plans
from omamods.nexus_api import NexusFile
from omamods.nexus_config import UserSettings
from omamods.install_records import file_state_path, recorded_file_id
from omamods.nexus_workflow import (
    LocalArchiveRequest,
    install_local_archive,
    revert_mod_files,
)
from omamods.pak_archive import PlannedAsset
from omamods.re_engine_layout import BASE_PAK
from omamods.re_pak_archive import (
    mod_files,
    patch_pak_variants,
    plan_patch_paks,
    write_packed_pak,
)
from omamods.re_pak_writer import (
    ENTRY,
    HEADER,
    murmur3_32,
    pak_major_version,
    path_hashes,
    write_re_pak,
)
from omamods.re_patch_chain import patch_name, require_packable_chain
from tests.fakes import FakeArchiveReader
from tests.test_re_engine import V4_HEADER, re7_game

MESH = "natives/stm/character/enemy/em2000/em2000/em2000.mdf2.21"
ASHLEY = (
    "modinfo.ini",
    "screenshot.png",
    "natives/",
    "natives/stm/",
    f"{MESH}",
    "natives/stm/character/enemy/em2000/em2050/em2050_face_alb.tex.35",
)


def read_entries(pak: bytes) -> list[tuple[int, ...]]:
    count = HEADER.unpack_from(pak)[4]
    return [ENTRY.unpack_from(pak, HEADER.size + i * ENTRY.size) for i in range(count)]


class HashTests(unittest.TestCase):
    def test_murmur3_matches_the_reference_vectors(self) -> None:
        self.assertEqual(murmur3_32(b"", 0), 0)
        self.assertEqual(murmur3_32(b"hello", 0), 0x248BFA47)

    def test_path_hash_matches_re7s_own_table(self) -> None:
        # Read from RE7's re_chunk_000.pak, which holds this mesh material.
        self.assertEqual(path_hashes(MESH), (649117905, 1535612681))

    def test_case_does_not_change_the_hashes(self) -> None:
        self.assertEqual(path_hashes(MESH.upper()), path_hashes(MESH))


class WriterTests(unittest.TestCase):
    def test_entries_point_at_the_contents(self) -> None:
        out = BytesIO()
        files = (
            ("natives/a", lambda s: s.write(b"one")),
            ("natives/b", lambda s: s.write(b"two!")),
        )
        write_re_pak(out, files)
        pak = out.getvalue()
        self.assertEqual(HEADER.unpack_from(pak)[:5], (b"KPKA", 4, 0, 0, 2))
        entries = read_entries(pak)
        self.assertEqual(entries[0][:2], path_hashes("natives/a"))
        offset, size = entries[1][2], entries[1][3]
        self.assertEqual(pak[offset : offset + size], b"two!")
        self.assertEqual(entries[1][4:6], (4, 0))

    def test_version_reads_only_kpka(self) -> None:
        self.assertEqual(pak_major_version(V4_HEADER), 4)
        self.assertIsNone(pak_major_version(b"PK\x03\x04" + bytes(12)))
        self.assertIsNone(pak_major_version(b"KPKA"))


class NativesPlanTests(unittest.TestCase):
    def test_fluffy_archive_becomes_one_packed_pak(self) -> None:
        (asset,) = plan_patch_paks(ASHLEY, re7_game(), None)
        self.assertTrue(asset.next_patch)
        self.assertEqual([path for _, path in asset.packed], sorted(ASHLEY[4:]))

    def test_folders_and_extras_are_skipped(self) -> None:
        names = [file.member for file in mod_files(ASHLEY)]
        self.assertEqual(names, sorted(ASHLEY[4:]))

    def test_rar_folders_without_a_slash_are_skipped(self) -> None:
        # bsdtar's RAR listing of Nexus RE7 mod 155 names "natives/stm" bare.
        members = ("natives", "natives/stm", f"{MESH}")
        self.assertEqual([f.member for f in mod_files(members)], [MESH])

    def test_paks_and_natives_install_together(self) -> None:
        planned = plan_patch_paks(
            ("Mod/a.pak", "Mod/natives/stm/x.tex"), re7_game(), None
        )
        self.assertEqual([a.target.name for a in planned], ["a.pak", "natives.pak"])

    def test_variant_root_is_the_folder_above_natives(self) -> None:
        members = ("Zoe DLC/natives/STM/a.mesh", "Zoe RT/natives/STM/a.mesh")
        self.assertEqual(patch_pak_variants(members), ("Zoe DLC", "Zoe RT"))
        (asset,) = plan_patch_paks(members, re7_game(), "Zoe RT")
        self.assertEqual(
            asset.packed, (("Zoe RT/natives/STM/a.mesh", "natives/STM/a.mesh"),)
        )

    def test_paths_differing_only_in_case_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "ignoring case"):
            plan_patch_paks(("natives/STM/a", "natives/stm/A"), re7_game(), None)

    def test_preview_counts_packed_files(self) -> None:
        (asset,) = plan_patch_paks(ASHLEY, re7_game(), None)
        plan = FilePlan(NexusFile(1, "Ashley.rar", "MAIN", 0), None, (asset,))
        self.assertIn("2 natives/ files, packed", describe_plans((plan,)))


class PackedInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "RE7"
        self.root.mkdir()
        (self.root / BASE_PAK).write_bytes(V4_HEADER)
        self.settings = UserSettings("", base / "storage", {}, ())
        self.game = replace(re7_game(), install_root=self.root)
        self.source = base / "Ashley.rar"
        self.source.write_bytes(b"rar")
        self.reader = FakeArchiveReader({name: name.encode() for name in ASHLEY})

    def _install(self) -> None:
        request = LocalArchiveRequest(self.source, 155, 706, None)
        install_local_archive(self.game, self.settings, self.root, request, self.reader)

    def test_written_pak_holds_every_natives_file(self) -> None:
        self._install()
        pak = (self.root / patch_name(BASE_PAK, 1)).read_bytes()
        entries = read_entries(pak)
        self.assertEqual({e[:2] for e in entries}, {path_hashes(p) for p in ASHLEY[4:]})
        for entry in entries:
            content = pak[entry[2] : entry[2] + entry[3]]
            self.assertTrue(content.startswith(b"natives/stm/"))

    def test_older_pak_format_is_refused(self) -> None:
        (self.root / BASE_PAK).write_bytes(b"KPKA\x02" + bytes(11))
        with self.assertRaisesRegex(ValueError, "pak version=2"):
            self._install()
        self.assertFalse((self.root / patch_name(BASE_PAK, 1)).exists())

    def test_packable_chain_accepts_version_4(self) -> None:
        require_packable_chain(self.root, BASE_PAK)

    def test_write_packed_pak_streams_each_member(self) -> None:
        asset = PlannedAsset("natives", Path("natives.pak"), True, ((MESH, MESH),))
        out = BytesIO()
        write_packed_pak(self.source, asset, out, self.reader)
        self.assertTrue(out.getvalue().endswith(MESH.encode()))
        self.assertEqual(struct.unpack_from("<I", out.getvalue(), 8)[0], 1)


ZOE = {
    "Zoe RT/modinfo.ini": b"",
    "Zoe RT/natives/STM/a.mesh": b"rt",
    "Zoe DLC/natives/STM/ch9/a.mesh": b"dlc",
}


class VariantInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "RE7"
        self.root.mkdir()
        (self.root / BASE_PAK).write_bytes(V4_HEADER)
        self.settings = UserSettings("", base / "storage", {}, ())
        self.game = replace(re7_game(), install_root=self.root)
        self.source = base / "Zoe.zip"
        self.source.write_bytes(b"zip")

    def _install(self, option: str) -> None:
        request = LocalArchiveRequest(self.source, 275, 996, option)
        reader = FakeArchiveReader(ZOE)
        install_local_archive(self.game, self.settings, self.root, request, reader)

    def _patches(self) -> list[str]:
        return sorted(p.name for p in self.root.glob(f"{BASE_PAK}.patch_*"))

    def test_each_variant_takes_its_own_patch(self) -> None:
        self._install("Zoe DLC")
        self._install("Zoe RT")
        self.assertEqual(
            self._patches(), [patch_name(BASE_PAK, 1), patch_name(BASE_PAK, 2)]
        )

    def test_same_variant_twice_is_refused(self) -> None:
        self._install("Zoe RT")
        with self.assertRaisesRegex(ValueError, "revert first"):
            self._install("Zoe RT")

    def test_uninstalling_the_file_reverts_every_variant(self) -> None:
        self._install("Zoe DLC")
        self._install("Zoe RT")
        root = self.settings.storage_root
        self.assertEqual(revert_mod_files(self.game, root, 275, 996), 2)
        # Removed together, so no empty placeholder is left behind.
        self.assertEqual(self._patches(), [])

    def test_variant_records_have_their_own_names(self) -> None:
        root = self.settings.storage_root
        plain = file_state_path(root, self.game, 275, 996, None)
        variant = file_state_path(root, self.game, 275, 996, "Zoe RT")
        self.assertEqual(plain.name, "996.json")
        self.assertNotEqual(
            variant, file_state_path(root, self.game, 275, 996, "Zoe DLC")
        )
        self.assertEqual(recorded_file_id(variant), 996)


if __name__ == "__main__":
    unittest.main()
