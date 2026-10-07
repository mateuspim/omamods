"""Steam KeyValues parsing tests, including malformed metadata."""

import unittest

from omamods.keyvalues import keyvalues_block, parse_keyvalues


class KeyValuesTests(unittest.TestCase):
    def test_nested_values_comments_bom_and_spaces(self) -> None:
        parsed = parse_keyvalues(
            '\ufeff// steam\n"libraryfolders" { "0" { "path" "/a b" } }'
        )
        self.assertEqual(parsed, {"libraryfolders": {"0": {"path": "/a b"}}})

    def test_escapes_empty_and_unquoted_values(self) -> None:
        parsed = parse_keyvalues(
            r'key "a\\b\"c" empty "" plain value url "https://test"'
        )
        self.assertEqual(
            parsed,
            {"key": 'a\\b"c', "empty": "", "plain": "value", "url": "https://test"},
        )

    def test_invalid_structures(self) -> None:
        sources = (
            '"unfinished',
            '"key"',
            "a { b c",
            "a }",
            "}",
            "{",
            "a b a c",
            "a {} }",
        )
        for source in sources:
            with (
                self.subTest(source=source),
                self.assertRaisesRegex(ValueError, "expected"),
            ):
                parse_keyvalues(source)

    def test_depth_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "depth=17.*expected"):
            parse_keyvalues("a { " * 17 + "}" * 17)

    def test_empty_document(self) -> None:
        self.assertEqual(parse_keyvalues(" // no entries\n"), {})

    def test_require_block(self) -> None:
        self.assertEqual(keyvalues_block({"AppState": {}}, "AppState"), {})
        with self.assertRaisesRegex(ValueError, "AppState='text'.*expected"):
            keyvalues_block({"AppState": "text"}, "AppState")
