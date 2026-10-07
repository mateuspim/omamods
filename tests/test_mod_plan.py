"""Exercise which files a mod downloads and installs together."""

from pathlib import Path
import unittest

from omamods.mod_plan import (
    FilePlan,
    conflicting_targets,
    default_installs,
    describe_plans,
    preselected_download,
)
from omamods.nexus_api import NexusFile
from omamods.pak_archive import PlannedAsset
from omamods.staging import StagedMod


def nexus_file(file_id: int, category: str) -> NexusFile:
    return NexusFile(file_id, f"f{file_id}.zip", category, 0)


def plan(file_id: int, *targets: str) -> FilePlan:
    assets = tuple(PlannedAsset(t, Path(t)) for t in targets)
    return FilePlan(nexus_file(file_id, "MAIN"), None, assets)


class ModPlanTests(unittest.TestCase):
    def test_picker_skips_stale_files(self) -> None:
        self.assertTrue(preselected_download(nexus_file(1, "OPTIONAL")))
        self.assertFalse(preselected_download(nexus_file(1, "OLD_VERSION")))

    def test_install_mod_takes_staged_required_files_only(self) -> None:
        files = tuple(
            nexus_file(i, c)
            for i, c in enumerate(
                ("MAIN", "UPDATE", "OPTIONAL", "MAIN", "STAGED", "MAIN")
            )
        )
        archives = {i: Path(f"{i}.zip") for i in (0, 1, 2, 3, 4)}
        mod = StagedMod(1, None, files, archives, None, frozenset({3}))
        self.assertEqual([f.file_id for f in default_installs(mod)], [0, 1, 4])

    def test_conflicts_name_both_files(self) -> None:
        plans = (plan(1, "~mods/a.pak"), plan(2, "~mods/b.pak", "~mods/a.pak"))
        self.assertEqual(
            conflicting_targets(plans), ("~mods/a.pak: f1.zip and f2.zip",)
        )
        self.assertEqual(conflicting_targets(plans[:1]), ())

    def test_description_lists_targets_per_file(self) -> None:
        text = describe_plans((plan(1, "~mods/a.pak"),))
        self.assertEqual(text, "f1.zip\n  Paks/~mods/a.pak")


if __name__ == "__main__":
    unittest.main()
