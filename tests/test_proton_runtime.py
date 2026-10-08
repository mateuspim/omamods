"""Read the Visual C++ runtime version in a Steam game's Proton prefix."""

from pathlib import Path
import struct
import unittest

from omamods.launch_options_advice import launch_options_advice
from omamods.proton_runtime import (
    file_version,
    is_outdated_runtime,
    msvc_runtime_version,
    steam_prefix,
    vcrun_command,
)
from omamods.red_frameworks import CET_MOD_ID, RED4EXT_MOD_ID
from tests.fakes import FakeDllFiles, version_resource

ROOT = Path("/lib/steamapps/common/Cyberpunk 2077")
PREFIX = Path("/lib/steamapps/compatdata/1091500/pfx")
FIXED = 'WINEDLLOVERRIDES="version,winmm=n,b" %command%'


class VersionTests(unittest.TestCase):
    def test_reads_the_fixed_file_info(self) -> None:
        blob = b"MZ" + bytes(64) + version_resource(14, 28, 29334, 0)
        self.assertEqual(file_version(blob), (14, 28, 29334, 0))

    def test_skips_a_signature_lookalike_in_code(self) -> None:
        # Regression: CET's .asi has the signature bytes before its resources.
        lookalike = struct.pack("<II", 0xFEEF04BD, 0xDEADBEEF) + bytes(8)
        blob = lookalike + version_resource(1, 37, 1, 0)
        self.assertEqual(file_version(blob), (1, 37, 1, 0))

    def test_no_resource_is_none(self) -> None:
        self.assertIsNone(file_version(b"MZ" + bytes(100)))

    def test_prefix_sits_in_the_games_library(self) -> None:
        self.assertEqual(steam_prefix(ROOT, "1091500"), PREFIX)

    def test_runtime_version_from_the_prefix(self) -> None:
        dll = PREFIX / "drive_c/windows/system32/msvcp140.dll"
        files = FakeDllFiles({dll: version_resource(14, 44, 35211, 0)})
        self.assertEqual(msvc_runtime_version(PREFIX, files), (14, 44, 35211, 0))
        self.assertIsNone(msvc_runtime_version(Path("/none"), files))

    def test_outdated_below_14_40(self) -> None:
        self.assertTrue(is_outdated_runtime((14, 28, 29334, 0)))
        self.assertFalse(is_outdated_runtime((14, 40, 0, 0)))
        self.assertFalse(is_outdated_runtime(None))

    def test_fix_command_names_the_app(self) -> None:
        self.assertEqual(vcrun_command("1091500"), "protontricks 1091500 -q vcrun2022")


class RuntimeAdviceTests(unittest.TestCase):
    def test_old_runtime_with_a_loader_needs_vcrun(self) -> None:
        ids = frozenset({RED4EXT_MOD_ID, CET_MOD_ID})
        advice = launch_options_advice((FIXED,), ids, (14, 28, 0, 0), "1091500")
        self.assertTrue(advice.needed)
        self.assertEqual(advice.missing, ())
        self.assertEqual(advice.runtime_fix, "protontricks 1091500 -q vcrun2022")

    def test_old_runtime_without_loaders_is_fine(self) -> None:
        advice = launch_options_advice((FIXED,), frozenset({4198}), (14, 28, 0, 0), "1")
        self.assertFalse(advice.needed)

    def test_current_runtime_is_fine(self) -> None:
        ids = frozenset({CET_MOD_ID})
        advice = launch_options_advice((FIXED,), ids, (14, 44, 0, 0), "1091500")
        self.assertIsNone(advice.runtime_fix)


if __name__ == "__main__":
    unittest.main()
