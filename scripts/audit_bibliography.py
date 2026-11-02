#!/usr/bin/env python3
"""Audit citation coverage, metadata completeness, and ledger consistency."""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT.parent / "paper"
BUNDLED_BIB = ROOT / "literature" / "references.bib"
CITATION_KEYS = ROOT / "literature" / "cited-keys.txt"
PAPER_BIB = PAPER / "references.bib"
BIB = PAPER_BIB if PAPER_BIB.exists() else BUNDLED_BIB
CALIBRATION = ROOT / "literature-calibration.csv"
TEX_FILES = (PAPER / "main.tex", PAPER / "supplement-content.tex")
DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
YEAR = re.compile(r"^(19|20)\d{2}$")


class AuditError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


class _BibParser:
    """Parse literal BibTeX fields without interpreting TeX or string macros.

    Supports nested braced/quoted values, numeric literals, literal # joins,
    multiple fields per line and outside-value percent comments. Unsupported
    directives/string identifiers fail explicitly rather than corrupting fields.
    """

    def __init__(self, text: str):
        self.text = text
        self.position = 0

    def skip(self) -> None:
        while self.position < len(self.text):
            if self.text[self.position].isspace():
                self.position += 1
            elif self.text[self.position] == "%":
                end = self.text.find("\n", self.position)
                self.position = len(self.text) if end < 0 else end + 1
            else:
                break

    def take(self, literal: str) -> None:
        self.skip()
        require(self.text.startswith(literal, self.position),
                f"expected {literal!r} at BibTeX offset {self.position}")
        self.position += len(literal)

    def token(self, pattern: str) -> str:
        self.skip()
        match = re.match(pattern, self.text[self.position:])
        require(match is not None, f"invalid BibTeX token at offset {self.position}")
        self.position += len(match.group())
        return match.group()

    def literal(self) -> str:
        self.skip()
        require(self.position < len(self.text), "unterminated BibTeX value")
        opening = self.text[self.position]
        if opening not in '{"':
            return self.token(r"[0-9]+")
        self.position += 1
        start = self.position
        depth = 0
        while self.position < len(self.text):
            character = self.text[self.position]
            if character == "\\":
                self.position += 2
                continue
            if character == "}":
                if opening == "{" and depth == 0:
                    result = self.text[start:self.position]
                    self.position += 1
                    return result
                require(depth > 0, "unmatched brace in quoted BibTeX value")
                depth -= 1
            elif character == "{":
                depth += 1
            elif character == '"' and opening == '"' and depth == 0:
                result = self.text[start:self.position]
                self.position += 1
                return result
            self.position += 1
        raise AuditError("unterminated BibTeX value")

    def value(self) -> str:
        parts = [self.literal()]
        self.skip()
        while self.text.startswith("#", self.position):
            self.position += 1
            parts.append(self.literal())
            self.skip()
        return "".join(parts).strip()

    def parse(self) -> dict[str, dict[str, str]]:
        entries: dict[str, dict[str, str]] = {}
        self.skip()
        while self.position < len(self.text):
            self.take("@")
            entry_type = self.token(r"[A-Za-z][A-Za-z0-9_-]*").lower()
            require(entry_type not in {"string", "preamble", "comment"},
                    f"unsupported BibTeX directive: {entry_type}")
            self.skip()
            opening = self.text[self.position:self.position + 1]
            require(opening in {"{", "("}, "missing BibTeX entry delimiter")
            self.position += 1
            closing = "}" if opening == "{" else ")"
            key = self.token(r"[^\s,{}()]+")
            require(key not in entries, f"duplicate BibTeX key: {key}")
            self.take(",")
            entry = {"entry_type": entry_type}
            self.skip()
            while not self.text.startswith(closing, self.position):
                name = self.token(r"[A-Za-z][A-Za-z0-9_-]*").lower()
                require(name not in entry, f"duplicate field {name} in {key}")
                self.take("=")
                value = self.value()
                require(value, f"empty field {name} in {key}")
                entry[name] = value
                self.skip()
                if self.text.startswith(closing, self.position):
                    break
                self.take(",")
                self.skip()
            self.take(closing)
            entries[key] = entry
            self.skip()
        return entries


def parse_bib(path: Path) -> dict[str, dict[str, str]]:
    return _BibParser(path.read_text(encoding="utf-8-sig")).parse()


def validate_entry_metadata(key: str, entry: dict[str, str]) -> None:
    for field in ("author", "title", "year"):
        require(entry.get(field, "").strip(), f"{key} lacks {field}")
    require(YEAR.fullmatch(entry["year"]) is not None, f"invalid year for {key}")
    entry_type = entry["entry_type"]
    if entry_type == "misc":
        require(entry.get("url", "").startswith("https://"),
                f"{key} lacks a stable preprint/repository URL")
        require(any(entry.get(field) for field in ("eprint", "note", "howpublished")),
                f"{key} lacks preprint/repository description")
    else:
        venue_field = {"article": "journal", "inproceedings": "booktitle",
                       "incollection": "booktitle"}.get(entry_type)
        require(venue_field is not None, f"unsupported bibliography entry type: {entry_type}")
        require(entry.get(venue_field, "").strip(), f"{key} lacks {venue_field}")


def normalize_title(value: str) -> str:
    value = re.sub(r"\\[a-zA-Z]+\s*", "", value)
    value = re.sub(r"[{}\\]", "", value)
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def inventory_keys() -> set[str]:
    lines = [
        line.strip()
        for line in CITATION_KEYS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    require(len(lines) == len(set(lines)), "duplicate citation key in standalone inventory")
    return set(lines)


def manuscript_cited_keys() -> set[str] | None:
    if not all(path.exists() for path in TEX_FILES):
        return None
    text = "\n".join(path.read_text(encoding="utf-8") for path in TEX_FILES)
    require("\\nocite" not in text, "\\nocite is not permitted for count padding")
    result: set[str] = set()
    for group in re.findall(r"\\cite(?:\[[^\]]*\])?\{([^}]*)\}", text):
        result.update(piece.strip() for piece in group.split(",") if piece.strip())
    return result


def cited_keys() -> set[str]:
    inventory = inventory_keys()
    manuscript = manuscript_cited_keys()
    if manuscript is not None:
        require(manuscript == inventory, "manuscript citations and standalone citation inventory differ")
    return inventory


def calibration_rows() -> list[dict[str, str]]:
    with CALIBRATION.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None, "literature calibration has no header")
        required = {
            "cite_key", "title", "authors", "year", "venue", "identifier",
            "category", "manuscript_role", "project_delta", "manuscript_location",
            "source_anchor", "verification_scope", "status",
        }
        require(required.issubset(reader.fieldnames), "literature calibration schema changed")
        rows = list(reader)
    return rows


def main() -> int:
    entries = parse_bib(BIB)
    bundled_entries = parse_bib(BUNDLED_BIB)
    require(entries == bundled_entries, "paper bibliography and standalone bibliography snapshot differ")
    citations = cited_keys()
    ledger = calibration_rows()
    ledger_keys = [row["cite_key"] for row in ledger]

    require(len(entries) >= 55, "fewer than 55 unique scholarly references")
    require(len(set(ledger_keys)) == len(ledger_keys), "duplicate calibration cite_key")
    require(set(entries) == citations, "BibTeX and citation key sets differ")
    require(set(entries) == set(ledger_keys),
            "calibration key sets differ; missing=" + repr(sorted(set(entries) - set(ledger_keys)))
            + "; unexpected=" + repr(sorted(set(ledger_keys) - set(entries))))

    seen_titles: dict[str, str] = {}
    seen_dois: dict[str, str] = {}
    seen_roles: dict[str, str] = {}
    seen_deltas: dict[str, str] = {}
    ledger_by_key = {row["cite_key"]: row for row in ledger}
    for key, entry in entries.items():
        validate_entry_metadata(key, entry)
        title_key = normalize_title(entry["title"])
        require(title_key and title_key not in seen_titles, f"duplicate normalized title: {key}/{seen_titles.get(title_key)}")
        seen_titles[title_key] = key
        doi = entry.get("doi", "").lower()
        if doi:
            require(DOI.fullmatch(doi) is not None, f"invalid DOI syntax for {key}")
            require(doi not in seen_dois, f"duplicate DOI: {key}/{seen_dois.get(doi)}")
            seen_dois[doi] = key

        row = ledger_by_key[key]
        require(row["year"] == entry["year"], f"year mismatch for {key}")
        require(normalize_title(row["title"]) == title_key, f"title mismatch for {key}")
        require(row["authors"].strip() and row["venue"].strip(), f"incomplete ledger metadata for {key}")
        role = row["manuscript_role"].strip()
        delta = row["project_delta"].strip()
        require(len(role) >= 80 and len(delta) >= 80, f"comparison scope is too generic for {key}")
        require(row["source_anchor"].strip(), f"missing source anchor for {key}")
        require(row["manuscript_location"].strip(), f"missing manuscript location for {key}")
        require(row["status"] == "cited in manuscript", f"unexpected citation status for {key}")
        role_key = re.sub(r"\s+", " ", role.lower())
        delta_key = re.sub(r"\s+", " ", delta.lower())
        require(role_key not in seen_roles, f"duplicate manuscript role: {key}/{seen_roles.get(role_key)}")
        require(delta_key not in seen_deltas, f"duplicate project delta: {key}/{seen_deltas.get(delta_key)}")
        seen_roles[role_key] = key
        seen_deltas[delta_key] = key
        scope = row["verification_scope"].lower()
        require("metadata checked" in scope and "source anchor" in scope, f"verification scope missing for {key}")
        identifier = row["identifier"].strip()
        if doi:
            require(identifier.lower() == f"doi:{doi}", f"DOI ledger mismatch for {key}")
        else:
            require(
                "stable venue record" in identifier.lower() or identifier.startswith("https://"),
                f"non-DOI record lacks a stable venue record or URL for {key}",
            )

    print(
        f"PASS: {len(entries)} unique cited references; {len(seen_dois)} unique DOIs; "
        "BibTeX/citation/calibration sets equal in full and standalone layouts; "
        "per-paper roles and source anchors present; "
        "no nocite or duplicate title/identifier"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AuditError, OSError, csv.Error) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
