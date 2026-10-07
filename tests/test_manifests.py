"""Manifest validation and safe YAML boundary tests."""

from pathlib import Path
import unittest

from omamods.manifests import load_catalog, validate_manifest
from omamods.yaml_codec import SafeYamlDecoder
from tests.fakes import FakeFiles, sample_fields

INVALID_FIELDS: tuple[tuple[str, object], ...] = (
    ("id", "../demo"),
    ("id", "Demo"),
    ("id", ""),
    ("name", 42),
    ("name", "  "),
    ("status", "unknown"),
    ("platforms", "steam"),
    ("platforms", []),
    ("platforms", [42]),
    ("platforms", ["steam", "gog"]),
    ("adapter", "overlay"),
    ("notes", [""]),
    ("steam_app_id", True),
    ("steam_app_id", -1),
    ("steam_app_id", 0),
    ("steam_app_id", "42"),
)


class ManifestTests(unittest.TestCase):
    def test_minimal_manifest_and_optional_fields(self) -> None:
        fields = sample_fields()
        fields.pop("steam_app_id")
        manifest = validate_manifest(fields)
        self.assertEqual(manifest.id, "demo")
        self.assertEqual(manifest.notes, ())
        self.assertIsNone(manifest.steam_app_id)

    def test_known_id_and_notes(self) -> None:
        fields = sample_fields()
        fields["notes"] = ["Verify the loader first."]
        manifest = validate_manifest(fields)
        self.assertEqual(manifest.steam_app_id, 42)
        self.assertEqual(manifest.notes, ("Verify the loader first.",))

    def test_invalid_shapes_and_unknown_fields(self) -> None:
        for value in (None, [], "demo", {1: "demo"}, {"typo": 42}):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "expected"),
            ):
                validate_manifest(value)

    def test_invalid_fields(self) -> None:
        for field, value in INVALID_FIELDS:
            with (
                self.subTest(field=field, value=value),
                self.assertRaisesRegex(ValueError, "expected"),
            ):
                validate_manifest(sample_fields() | {field: value})

    def test_load_catalog(self) -> None:
        source = "id: demo\nname: Demo\nstatus: discovery\nplatforms: [steam]\nadapter: undecided"
        files = FakeFiles({Path("games/demo/game.yml"): source}, (Path("games"),))
        result = load_catalog(Path("games"), files, SafeYamlDecoder())
        self.assertEqual([game.id for game in result], ["demo"])

    def test_catalog_directory_is_required(self) -> None:
        for files in (FakeFiles(), FakeFiles(directories=(Path("games"),))):
            with self.assertRaisesRegex(ValueError, "games.*expected"):
                load_catalog(Path("games"), files, SafeYamlDecoder())

    def test_manifest_context_and_directory_identity(self) -> None:
        source = "id: demo\nname: Demo\nstatus: discovery\nplatforms: [steam]\nadapter: undecided"
        files = FakeFiles({Path("games/wrong/game.yml"): source}, (Path("games"),))
        with self.assertRaisesRegex(
            ValueError, "games/wrong/game.yml.*expected directory name"
        ):
            load_catalog(Path("games"), files, SafeYamlDecoder())


class YamlTests(unittest.TestCase):
    def test_safe_decoding(self) -> None:
        self.assertEqual(SafeYamlDecoder().decode("id: demo"), {"id": "demo"})

    def test_reject_invalid_unsafe_or_ambiguous_yaml(self) -> None:
        sources = (
            "id: [",
            "!!python/object/apply:os.system ['false']",
            "id: demo\nid: other",
            "1: demo",
            "? [a, b]\n: demo",
        )
        for source in sources:
            with (
                self.subTest(source=source),
                self.assertRaisesRegex(ValueError, "expected"),
            ):
                SafeYamlDecoder().decode(source)
