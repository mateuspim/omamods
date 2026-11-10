"""The hint line names only the keys that act on the selected mod or file."""

from pathlib import Path
import unittest

from omamods.mod_sites import PATCH_SITE
from omamods.nexus_api import NexusFile
from omamods.staging import StagedMod
from omamods.tui.context_hints import (
    file_pairs,
    key_hints,
    mod_list_pairs,
    patch_pairs,
)

MAIN = NexusFile(1, "main.zip", "MAIN", 10, "Main")
EXTRA = NexusFile(2, "extra.zip", "OPTIONAL", 10, "Extra")


def staged(archives: tuple[int, ...], installed: tuple[int, ...]) -> StagedMod:
    """A two-file mod with the given files downloaded and installed."""
    paths = {file_id: Path(f"/a/{file_id}.zip") for file_id in archives}
    return StagedMod(7, None, (MAIN, EXTRA), paths, None, frozenset(installed))


def keys(pairs: tuple[tuple[str, str], ...]) -> list[str]:
    return [key for key, _ in pairs]


class ContextHintTests(unittest.TestCase):
    def test_key_hints_format(self) -> None:
        self.assertEqual(
            key_hints(("i", "install"), ("u", "uninstall")),
            "[b]i[/] install   [b]u[/] uninstall",
        )

    def test_page_only_mod_offers_download_and_dropping_the_mod(self) -> None:
        pairs = file_pairs(staged((), ()), MAIN)
        self.assertEqual(
            pairs, (("enter", "download"), ("d", "download"), ("x", "remove mod"))
        )

    def test_other_file_downloaded_means_no_remove_on_this_one(self) -> None:
        self.assertEqual(keys(file_pairs(staged((2,), ()), MAIN)), ["enter", "d"])

    def test_downloaded_file_offers_install_and_remove(self) -> None:
        self.assertEqual(keys(file_pairs(staged((1,), ()), MAIN)), ["enter", "x"])

    def test_installed_file_offers_load_last(self) -> None:
        pairs = file_pairs(staged((1,), (1,)), MAIN)
        self.assertEqual(keys(pairs), ["enter", "x", "P"])
        self.assertEqual(pairs[0], ("enter", "uninstall"))

    def test_mod_list_names_mod_keys_and_the_selected_file(self) -> None:
        mod = staged((1,), (1,))
        self.assertEqual(
            keys(mod_list_pairs(mod, MAIN)), ["u", "x", "enter", "w", "a", "/"]
        )
        self.assertEqual(
            keys(mod_list_pairs(mod, EXTRA)), ["u", "d", "enter", "w", "a", "/"]
        )
        self.assertEqual(keys(mod_list_pairs(staged((2,), ()), MAIN))[0], "i")

    def test_no_mod_offers_add(self) -> None:
        self.assertEqual(keys(mod_list_pairs(None, None)), ["a", "/"])

    def test_patch_keys_follow_its_state(self) -> None:
        mod = StagedMod(1, None, (MAIN,), {}, None, frozenset(), PATCH_SITE)
        self.assertEqual(keys(patch_pairs(mod)), ["i", "x"])
        self.assertEqual(file_pairs(mod, MAIN)[0], ("enter", "patch"))
        patched = StagedMod(1, None, (MAIN,), {}, None, frozenset({1}), PATCH_SITE)
        self.assertEqual(keys(mod_list_pairs(patched, MAIN)), ["u", "x", "w"])
        self.assertEqual(file_pairs(patched, MAIN)[0], ("enter", "restore"))


if __name__ == "__main__":
    unittest.main()
