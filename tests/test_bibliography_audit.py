"""Literal BibTeX and fail-closed calibration controls; no source-reading claim."""
import contextlib
import copy
import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import audit_bibliography as audit


def serialize(entries):
    return "\n".join(
        "@" + entry["entry_type"] + "{" + key + ",\n"
        + "".join("  " + field + " = {" + value + "},\n"
                  for field, value in entry.items() if field != "entry_type")
        + "}\n" for key, entry in entries.items()
    )


class BibTeXParserTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "references.bib"
            path.write_text(text, encoding="utf-8")
            return audit.parse_bib(path)

    def test_delivered_same_line_fields_remain_distinct(self):
        entries = audit.parse_bib(audit.BIB)
        first = entries["baquero2017pureop"]
        self.assertEqual(first["title"], "Pure Operation-Based Replicated Data Types")
        self.assertEqual(first["year"], "2017")
        self.assertEqual(first["eprint"], "1710.04469")
        self.assertEqual(first["archiveprefix"], "arXiv")
        self.assertEqual(first["doi"], "10.48550/arXiv.1710.04469")
        self.assertEqual(first["url"], "https://arxiv.org/abs/1710.04469")
        second = entries["kolman2009forbidden"]
        self.assertEqual(second["title"], "On the Complexity of Paths Avoiding Forbidden Pairs")
        self.assertEqual(second["year"], "2009")
        self.assertEqual(second["note"], "Author preprint, April 29")

    def test_multiline_nested_braces_escapes_quotes_and_numeric_year(self):
        entries = self.parse(r'''% outside-value comment
@Article(Key, author = {An {\"o} Author},
title = "A {nested \"quote\"}
title", year = 2020, journal = "Journal " # {Name},
url = {https://example.invalid/a%20b})''')
        self.assertEqual(entries["Key"]["year"], "2020")
        self.assertEqual(entries["Key"]["journal"], "Journal Name")
        self.assertIn(r'{\"o}', entries["Key"]["author"])
        self.assertIn("\n", entries["Key"]["title"])
        self.assertEqual(entries["Key"]["url"], "https://example.invalid/a%20b")

    def test_duplicate_key_or_field_is_rejected(self):
        for text in ("@misc{k,title={a},title={b}}",
                     "@misc{k,title={a}} @misc{k,title={b}}"):
            with self.subTest(text=text), self.assertRaisesRegex(audit.AuditError, "duplicate"):
                self.parse(text)

    def test_unbalanced_missing_comma_empty_and_trailing_garbage_fail(self):
        for text in ("@misc{k,title={unclosed}", "@misc{k,title={a} year=2020}",
                     "@misc{k,title={}}", "@misc{k,title={a}} garbage",
                     '@misc{k,title="unclosed}'):
            with self.subTest(text=text), self.assertRaises(audit.AuditError):
                self.parse(text)

    def test_unsupported_string_expansion_fails_explicitly(self):
        for text in ("@string{j={Journal}}", "@article{k,journal=unknownMacro}"):
            with self.subTest(text=text), self.assertRaises(audit.AuditError):
                self.parse(text)

    def test_delivered_entries_validate_by_type_without_fake_venues(self):
        entries = audit.parse_bib(audit.BIB)
        self.assertEqual(len(entries), 72)
        for key, entry in entries.items():
            audit.validate_entry_metadata(key, entry)
        for key in ("baquero2017pureop", "kolman2009forbidden"):
            self.assertNotIn("booktitle", entries[key])
            self.assertNotIn("journal", entries[key])

    def test_article_and_preprint_required_fields_are_not_weakened(self):
        entries = audit.parse_bib(audit.BIB)
        mutations = [
            ("baquero2017pureop", "url", "stable preprint/repository URL"),
            ("kolman2009forbidden", "note", "preprint/repository description"),
            ("weidner2025fugue", "journal", "lacks journal"),
            ("wolf2018mutex", "booktitle", "lacks booktitle"),
            ("kohler2013games", "booktitle", "lacks booktitle"),
        ]
        for key, field, message in mutations:
            entry = copy.deepcopy(entries[key])
            del entry[field]
            with self.subTest(key=key, field=field), self.assertRaisesRegex(audit.AuditError, message):
                audit.validate_entry_metadata(key, entry)

    def test_invalid_year_is_rejected(self):
        entry = audit.parse_bib(audit.BIB)["baquero2017pureop"]
        entry["year"] = "2017, url=other"
        with self.assertRaisesRegex(audit.AuditError, "invalid year"):
            audit.validate_entry_metadata("test", entry)


class BibliographyBindingTests(unittest.TestCase):
    def test_live_snapshot_and_inventory_match_all_72_citations(self):
        entries = audit.parse_bib(audit.BIB)
        self.assertEqual(entries, audit.parse_bib(ROOT / "literature/references.bib"))
        self.assertEqual(set(entries), audit.inventory_keys())
        manuscript_keys = audit.manuscript_cited_keys()
        if manuscript_keys is not None:
            self.assertEqual(set(entries), manuscript_keys)

    def test_missing_snapshot_entry_is_rejected_before_calibration(self):
        entries = audit.parse_bib(ROOT / "literature/references.bib")
        del entries["baquero2017pureop"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "references.bib"
            path.write_text(serialize(entries), encoding="utf-8")
            with patch.object(audit, "BUNDLED_BIB", path):
                with self.assertRaisesRegex(audit.AuditError, "snapshot differ"):
                    audit.main()

    def test_absent_calibration_is_not_silently_certified(self):
        # Delete an actual row in memory; do not invent a source-support receipt.
        rows = audit.calibration_rows()
        rows = [row for row in rows if row["cite_key"] != "wolf2018mutex"]
        with patch.object(audit, "calibration_rows", return_value=rows):
            with self.assertRaisesRegex(audit.AuditError, "calibration key sets differ") as failure:
                audit.main()
        self.assertIn("wolf2018mutex", str(failure.exception))

    def test_each_added_calibration_row_is_required(self):
        retained = audit.calibration_rows()
        for key in ("baquero2017pureop", "kolman2009forbidden"):
            self.assertIn(key, {row["cite_key"] for row in retained})
            rows = [row for row in retained if row["cite_key"] != key]
            with self.subTest(key=key), patch.object(audit, "calibration_rows", return_value=rows):
                with self.assertRaisesRegex(audit.AuditError, "calibration key sets differ") as failure:
                    audit.main()
            self.assertIn(key, str(failure.exception))

    def test_existing_calibrated_subset_audits_in_full_and_standalone_layouts(self):
        # A private metadata fixture, not a rewritten manuscript or new reading.
        rows = audit.calibration_rows()
        supported = {row["cite_key"] for row in rows}
        entries = {key: entry for key, entry in audit.parse_bib(
            ROOT / "literature/references.bib").items() if key in supported}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bib = root / "references.bib"
            bib.write_text(serialize(entries), encoding="utf-8")
            keys = root / "cited-keys.txt"
            keys.write_text("\n".join(sorted(entries)) + "\n", encoding="utf-8")
            calibration = root / "calibration.csv"
            with calibration.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            main, supplement = root / "main.tex", root / "supplement.tex"
            for standalone in (False, True):
                if not standalone:
                    main.write_text(r"\cite{" + ",".join(entries) + "}", encoding="utf-8")
                    supplement.write_text("", encoding="utf-8")
                tex_files = (root / "absent.tex", root / "also-absent.tex") if standalone else (main, supplement)
                with self.subTest(standalone=standalone), contextlib.ExitStack() as stack:
                    for name, value in (("BIB", bib), ("BUNDLED_BIB", bib),
                                        ("CITATION_KEYS", keys), ("CALIBRATION", calibration),
                                        ("TEX_FILES", tex_files)):
                        stack.enter_context(patch.object(audit, name, value))
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(audit.main(), 0)


if __name__ == "__main__":
    unittest.main()
