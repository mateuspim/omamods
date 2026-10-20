"""Decide which mods clash over a package and which one the game shows."""

import json
from pathlib import Path
import tempfile
import unittest

from omamods.asset_collisions import (
    ModContainer,
    collision_between,
    container_entries,
    describe_collision,
    entry_key,
    find_collisions,
    internal_collisions,
    load_rank,
    short_package,
)
from omamods.byte_ranges import BytesRanges, FileRanges
from omamods.installed_containers import ContainerIndexes, recorded_containers
from tests.pak_builders import utoc_bytes

JACKET = "game/content/art/hero/jacket"


def container(owner: str, name: str, *keys: str) -> ModContainer:
    return ModContainer(owner, name, frozenset(keys))


class EntryKeyTests(unittest.TestCase):
    def test_package_files_share_one_key(self) -> None:
        for suffix in (".uasset", ".UBULK", ".uexp"):
            with self.subTest(suffix=suffix):
                path = f"../../../Game/Content/Art/Hero/Jacket{suffix}"
                self.assertEqual(entry_key(path), JACKET)

    def test_loose_files_keep_their_extension(self) -> None:
        bank = "../../../Game/Content/Sound/Voice.bnk"
        self.assertEqual(entry_key(bank), "game/content/sound/voice.bnk")

    def test_mod_kit_label_is_ignored(self) -> None:
        self.assertIsNone(entry_key("../../../Game/Content/Art/Label_MyMod.uasset"))
        paths = ("../../../Game/Content/Art/Label_MyMod.uasset", "A/B.uasset")
        self.assertEqual(container_entries(paths), frozenset({"a/b"}))


class LoadOrderTests(unittest.TestCase):
    def test_patch_numbers_outrank_names(self) -> None:
        self.assertGreater(load_rank("A_P"), load_rank("Zed"))
        self.assertGreater(load_rank("a_9_P"), load_rank("zzz_P"))
        self.assertEqual(load_rank("Mod_0_P")[0], load_rank("Mod_P")[0])

    def test_equal_patches_go_by_name_ignoring_case(self) -> None:
        self.assertGreater(load_rank("outfit_P"), load_rank("BodyTweaks_P"))

    def test_later_name_is_shown(self) -> None:
        skin = container("Body Tweaks", "BodyTweaks_P", JACKET)
        outfit = container("Outfit", "Outfit_P", JACKET)
        clash = collision_between(skin, outfit)
        assert clash is not None
        self.assertEqual((clash.shown, clash.hidden), (outfit, skin))
        self.assertEqual(clash.packages, (JACKET,))
        self.assertIsNone(collision_between(skin, container("X", "X_P", "a")))


class FindCollisionTests(unittest.TestCase):
    def test_compares_every_pair_across_sets(self) -> None:
        mine = (container("Outfit", "Outfit_P", JACKET, "b"),)
        others = (container("Skin", "Skin_P", JACKET), container("Y", "Y_P", "c"))
        self.assertEqual(len(find_collisions(mine, others)), 1)

    def test_internal_pairs_each_file_once(self) -> None:
        mine = (
            container("Outfit", "Fix_P", "physics"),
            container("Outfit", "Outfit_P", "physics"),
            container("Outfit", "Extra_P", "other"),
        )
        clashes = internal_collisions(mine)
        self.assertEqual([c.shown.name for c in clashes], ["Outfit_P"])

    def test_describes_both_sides(self) -> None:
        clash = collision_between(
            container("Skin", "Skin_P", JACKET, "a/x", "a/y", "a/z"),
            container("Outfit", "Outfit_P", JACKET, "a/x", "a/y", "a/z"),
        )
        assert clash is not None
        # "Skin_P" sorts after "Outfit_P", so Skin is the one shown.
        shown = describe_collision(clash, "Skin")
        self.assertTrue(shown.startswith("overrides Outfit: 4 asset(s)"))
        self.assertIn("+1 more); Skin_P loads over Outfit_P", shown)
        hidden = describe_collision(clash, "Outfit")
        self.assertTrue(hidden.startswith("hidden by Skin"))
        same = collision_between(
            container("P", "Fix_P", "k"), container("P", "B_P", "k")
        )
        assert same is not None
        self.assertTrue(describe_collision(same, "P").startswith("two of its files"))

    def test_short_package_keeps_the_last_part(self) -> None:
        self.assertEqual(short_package(JACKET), "jacket")


class InstalledContainerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paks = Path(self.temporary.name) / "Paks"
        (self.paks / "~mods").mkdir(parents=True)

    def _record(self, *relative: str) -> Path:
        record = Path(self.temporary.name) / "7.json"
        assets = [{"relative_path": path, "sha256": "x"} for path in relative]
        record.write_text(json.dumps({"paks": str(self.paks), "assets": assets}))
        return record

    def test_record_lists_only_safe_containers(self) -> None:
        record = self._record("~mods/A_P.utoc", "~mods/A_P.ucas", "../x.pak")
        self.assertEqual(recorded_containers(record), (self.paks / "~mods/A_P.utoc",))
        broken = Path(self.temporary.name) / "broken.json"
        broken.write_text("{}")
        with self.assertRaisesRegex(ValueError, "expected paks and assets"):
            recorded_containers(broken)

    def test_stub_pak_and_utoc_form_one_cached_container(self) -> None:
        utoc = self.paks / "~mods/A_P.utoc"
        utoc.write_bytes(utoc_bytes(("Art/Hero/Jacket.uasset",)))
        reads: list[Path] = []

        def counted(path: Path) -> FileRanges:
            reads.append(path)
            return FileRanges(path)

        indexes = ContainerIndexes(counted)
        found = indexes.containers("Outfit", [utoc])
        self.assertEqual(found, (container("Outfit", "A_P", JACKET),))
        indexes.containers("Outfit", [utoc])
        self.assertEqual(len(indexes.cache), 1)  # Second read hit the cache.
        self.assertEqual(len(reads), 2)  # Only the size was checked again.

    def test_bytes_ranges_slice(self) -> None:
        self.assertEqual(BytesRanges(b"abc").read(1, 5), b"bc")


if __name__ == "__main__":
    unittest.main()
