"""Tests for translation, RTL and locale-aware formatting.

Needs no Qt: the catalogues and formatters are plain data and plain functions,
which is exactly why they live outside the UI package's Qt-dependent modules.
"""

from __future__ import annotations

import re
import unittest

from alikhande.i18n import (
    EN,
    FA,
    LANGUAGES,
    code,
    current,
    fmt_count,
    fmt_percent,
    fmt_price,
    is_rtl,
    set_language,
    t,
    to_locale_digits,
    zone_relation_name,
)


class TestCatalogues(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_persian_covers_every_english_key(self):
        """A missing key falls back to English, which looks like a bug in the
        middle of a Persian sentence. The catalogue must be complete."""
        self.assertEqual(sorted(set(EN) - set(FA)), [])

    def test_persian_has_no_orphan_keys(self):
        """An extra Persian key means an English string was renamed and its
        translation was left behind — dead weight that reads as coverage."""
        self.assertEqual(sorted(set(FA) - set(EN)), [])

    def test_no_translation_is_left_empty(self):
        for catalogue, name in ((EN, "EN"), (FA, "FA")):
            for key, value in catalogue.items():
                self.assertTrue(value.strip(), f"{name}[{key}] is empty")

    def test_placeholders_match_between_languages(self):
        """A Persian string missing a ``{count}`` renders a sentence with a hole
        in it; one with an extra placeholder raises at format time."""
        placeholder = re.compile(r"\{(\w+)\}")
        for key, english in EN.items():
            self.assertEqual(
                sorted(placeholder.findall(english)),
                sorted(placeholder.findall(FA[key])),
                f"placeholder mismatch on {key}",
            )

    def test_persian_strings_actually_contain_persian(self):
        """Guards against a key that was copied across untranslated.

        Skips the ones that are legitimately identical in both — symbols,
        version-style values and the em-dash placeholder.
        """
        allowed_identical = {"common.none", "common.probability"}
        persian = re.compile(r"[؀-ۿ]")
        for key, value in FA.items():
            if key in allowed_identical:
                continue
            self.assertTrue(
                persian.search(value), f"FA[{key}] has no Persian characters: {value!r}"
            )


class TestLookup(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_lookup_follows_the_selected_language(self):
        set_language("en")
        self.assertEqual(t("nav.risk"), "Risk")
        set_language("fa")
        self.assertEqual(t("nav.risk"), "ریسک")

    def test_an_unknown_key_returns_itself(self):
        """Visibly broken beats invisibly blank: an empty label looks like a
        real empty value and can survive for months."""
        self.assertEqual(t("no.such.key"), "no.such.key")

    def test_an_unknown_language_falls_back_to_english(self):
        set_language("kl")
        self.assertEqual(current().code, "en")

    def test_interpolation_works(self):
        set_language("en")
        self.assertIn("7", t("dash.verdict.ready", count=7))

    def test_a_missing_placeholder_does_not_raise(self):
        """A malformed call must not take the window down."""
        self.assertIsInstance(t("dash.verdict.ready"), str)


class TestDirection(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_persian_is_rtl_and_english_is_not(self):
        set_language("fa")
        self.assertTrue(is_rtl())
        set_language("en")
        self.assertFalse(is_rtl())

    def test_every_language_names_itself_in_its_own_script(self):
        self.assertEqual(LANGUAGES["fa"].name, "فارسی")
        self.assertEqual(LANGUAGES["en"].name, "English")


class TestNumbers(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_prices_always_use_latin_digits(self):
        """Persian digits are not monospaced in the bundled fonts, so a column
        of them would not align — and every terminal shows prices in Latin."""
        set_language("fa")
        rendered = fmt_price(1.23456, 5)
        self.assertEqual(rendered, "1.23456")
        self.assertFalse(any(d in rendered for d in "۰۱۲۳۴۵۶۷۸۹"))

    def test_counts_follow_the_locale(self):
        set_language("fa")
        self.assertEqual(fmt_count(1247), "۱,۲۴۷")
        set_language("en")
        self.assertEqual(fmt_count(1247), "1,247")

    def test_percentages_follow_the_locale(self):
        set_language("fa")
        self.assertTrue(any(d in fmt_percent(0.25) for d in "۰۱۲۳۴۵۶۷۸۹"))

    def test_digit_mapping_leaves_other_characters_alone(self):
        set_language("fa")
        self.assertEqual(to_locale_digits("EURUSD 12"), "EURUSD ۱۲")


class TestVocabulary(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_known_refusal_codes_are_translated(self):
        set_language("fa")
        self.assertNotEqual(code("SPREAD_OR_QUOTE_BLOCK"), "spread or quote block")

    def test_a_code_with_arguments_is_stripped_before_lookup(self):
        set_language("en")
        self.assertEqual(code("SPREAD_OR_QUOTE_BLOCK(12)"), "spread or quote blocked")

    def test_an_unlisted_code_still_reads_as_words(self):
        self.assertEqual(code("SOME_NEW_CODE"), "some new code")

    def test_zone_relations_are_translated(self):
        set_language("fa")
        for name in ("INSIDE", "ABOVE", "BELOW", "UNAVAILABLE"):
            self.assertNotIn("zone.", zone_relation_name(name))


class TestGuide(unittest.TestCase):
    def test_every_guide_section_is_complete_in_both_languages(self):
        """Importing the guide module needs no Qt for this — the content table
        is module-level data."""
        import importlib.util
        import pathlib

        source = (
            pathlib.Path(__file__).resolve().parent.parent
            / "alikhande" / "ui" / "views" / "guide.py"
        ).read_text(encoding="utf-8")
        # Parsed rather than imported so this test runs in the Qt-free job too.
        import ast

        tree = ast.parse(source)
        guide = None
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "GUIDE":
                guide = ast.literal_eval(node.value)
        self.assertIsNotNone(guide, "GUIDE table not found")
        self.assertGreaterEqual(len(guide), 8)
        for section in guide:
            self.assertEqual(len(section), 5, "every section needs both languages")
            for part in section:
                self.assertTrue(str(part).strip())

    def test_the_persian_guide_is_actually_persian(self):
        import ast
        import pathlib
        import re

        source = (
            pathlib.Path(__file__).resolve().parent.parent
            / "alikhande" / "ui" / "views" / "guide.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        guide = next(
            ast.literal_eval(n.value)
            for n in tree.body
            if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "GUIDE"
        )
        persian = re.compile(r"[؀-ۿ]")
        for _, _, _, fa_title, fa_body in guide:
            self.assertTrue(persian.search(fa_title))
            self.assertTrue(persian.search(fa_body))


if __name__ == "__main__":
    unittest.main()
