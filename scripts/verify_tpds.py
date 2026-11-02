#!/usr/bin/env python3
"""Validate paired materializer measurements and exact topology responsiveness."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
D = RESULTS / "tpds"
# Declared campaign population, not inferred from the summaries being checked.
FAMILIES = ("sparse_cut", "dense_cut", "low_conflict")
SIZES = ("64", "128", "256", "512")
SEEDS = ("1", "2", "3", "4", "5")
REPETITIONS = ("0", "1", "2", "3", "4")
IMPLEMENTATIONS = ("reference", "indexed")
CASE_KEYS = {(f, n, s) for f in FAMILIES for n in SIZES for s in SEEDS}
SUMMARY_KEYS = {(f, n) for f in FAMILIES for n in SIZES}
RAW_KEYS = {(*case, arm, rep) for case in CASE_KEYS
            for arm in IMPLEMENTATIONS for rep in REPETITIONS}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def rows(name: str) -> list[dict[str, str]]:
    with (D / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def close(left: object, right: object) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-12)


def indexed_rows(records, fields, expected, label):
    lookup = {}
    for row in records:
        key = tuple(row[field] for field in fields)
        require(key not in lookup, f"{label}: duplicate identity {key}")
        lookup[key] = row
    require(set(lookup) == expected, f"{label}: incomplete or unexpected identity population")
    return lookup


def raw_cases(raw_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    indexed_rows(raw_rows, ("family", "handles", "seed", "implementation", "repetition"),
                 RAW_KEYS, "materializer raw")
    grouped: dict[tuple[str, str, str, str], dict[int, float]] = defaultdict(dict)
    for row in raw_rows:
        key = (row["family"], row["handles"], row["seed"], row["implementation"])
        repetition = int(row["repetition"])
        require(repetition not in grouped[key], "duplicate raw repetition")
        require(math.isfinite(float(row["seconds"])) and float(row["seconds"]) > 0
                and row["view_equal"] == "True", "invalid raw timing row")
        grouped[key][repetition] = float(row["seconds"])

    case_rows: list[dict[str, object]] = []
    identities = sorted({(r["family"], r["handles"], r["seed"]) for r in raw_rows})
    for family, handles, seed in identities:
        medians: dict[str, float] = {}
        for implementation in ("reference", "indexed"):
            values = grouped[(family, handles, seed, implementation)]
            require(set(values) == set(range(5)), "raw timing set lacks five repetitions")
            medians[implementation] = statistics.median(values.values())
        case_rows.append(
            {
                "family": family,
                "handles": handles,
                "seed": seed,
                "reference_seconds": medians["reference"],
                "indexed_seconds": medians["indexed"],
                "reference_over_indexed": medians["reference"] / medians["indexed"],
            }
        )

    return case_rows


def summarize_raw(raw_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    case_rows = raw_cases(raw_rows)
    summary: list[dict[str, object]] = []
    for family, handles in sorted({(r["family"], r["handles"]) for r in case_rows}):
        selected = [r for r in case_rows if (r["family"], r["handles"]) == (family, handles)]
        ratios = [float(r["reference_over_indexed"]) for r in selected]
        summary.append(
            {
                "family": family,
                "handles": handles,
                "cases": len(selected),
                "reference_median_ms": 1000 * statistics.median(float(r["reference_seconds"]) for r in selected),
                "indexed_median_ms": 1000 * statistics.median(float(r["indexed_seconds"]) for r in selected),
                "paired_speedup_median": statistics.median(ratios),
                "paired_speedup_min": min(ratios),
                "paired_speedup_max": max(ratios),
            }
        )
    return summary


def compare_summary(expected: list[dict[str, object]], observed: list[dict[str, str]], label: str) -> None:
    indexed_rows(expected, ("family", "handles"), SUMMARY_KEYS, f"{label} expected summary")
    lookup = indexed_rows(observed, ("family", "handles"), SUMMARY_KEYS, f"{label} summary")
    for row in expected:
        got = lookup[(str(row["family"]), str(row["handles"]))]
        require(int(got["cases"]) == int(row["cases"]), f"{label} case count differs")
        for field in (
            "reference_median_ms",
            "indexed_median_ms",
            "paired_speedup_median",
            "paired_speedup_min",
            "paired_speedup_max",
        ):
            require(close(got[field], row[field]), f"{label} {field} differs")


def main() -> None:
    raw = rows("materializer_raw.csv")
    cases = rows("materializer_cases.csv")
    summary = rows("materializer_summary.csv")
    require(len(raw) == 600 and len(cases) == 60 and len(summary) == 12, "incomplete benchmark matrix")

    final_recomputed = summarize_raw(raw)
    compare_summary(final_recomputed, summary, "final-current")

    families = set(FAMILIES)
    case_lookup = indexed_rows(cases, ("family", "handles", "seed"), CASE_KEYS, "materializer cases")
    for rebuilt in raw_cases(raw):
        case = case_lookup[tuple(rebuilt[k] for k in ("family", "handles", "seed"))]
        require(case["repetitions"] == "5", "case repetition count differs")
        for field in ("reference_seconds", "indexed_seconds", "reference_over_indexed"):
            require(close(case[field], rebuilt[field]), f"raw/case {field} differs")
    for case in cases:
        require(case["view_equal"] == "True" and int(case["cells"]) <= 80_000, "invalid evidence state")

    retained = json.loads((RESULTS / "reproduction.json").read_text(encoding="utf-8"))[
        "timing_replication"
    ]
    require("primary_raw_timings" not in retained, "unexpected primary raw timings appeared")
    primary_summary = retained["primary_summary"]
    indexed_rows(primary_summary, ("family", "handles"), SUMMARY_KEYS, "summary-only-primary")
    require(all(row["cases"] == "5" for row in primary_summary), "primary summary case count differs")
    clean_raw = retained["clean_raw_timings"]
    require(len(clean_raw) == 600, "clean raw timing set is incomplete")
    clean_recomputed = summarize_raw(clean_raw)
    compare_summary(clean_recomputed, retained["clean_summary"], "retained-clean")

    replications = rows("materializer_replications.csv")
    require(len(replications) == 9, "replication summary incomplete")
    require(
        {r["execution"] for r in replications}
        == {"summary-only-primary", "retained-clean", "final-current"},
        "replication evidence labels differ",
    )
    require({r["family"] for r in replications} == families, "replication family set differs")
    require({r["handles"] for r in replications} == {"512"}, "replication size differs")

    expected_rows: list[tuple[str, dict[str, object]]] = []
    expected_rows.extend(
        ("summary-only-primary", row)
        for row in primary_summary
        if str(row["handles"]) == "512"
    )
    expected_rows.extend(
        ("retained-clean", row)
        for row in clean_recomputed
        if str(row["handles"]) == "512"
    )
    expected_rows.extend(
        ("final-current", row)
        for row in final_recomputed
        if str(row["handles"]) == "512"
    )
    lookup = indexed_rows(replications, ("execution", "family"),
        {(execution, family) for execution in ("summary-only-primary", "retained-clean", "final-current")
         for family in FAMILIES}, "replication summary")
    for execution, row in expected_rows:
        got = lookup[(execution, str(row["family"]))]
        require(got["cases"] == "5", "replication case count differs")
        for field in (
            "reference_median_ms",
            "indexed_median_ms",
            "paired_speedup_median",
            "paired_speedup_min",
            "paired_speedup_max",
        ):
            require(close(got[field], row[field]), "replication value mismatch")
    for row in replications:
        if row["execution"] == "summary-only-primary":
            require(row["raw_records"] == "0", "summary-only primary must have zero raw records")
            require(row["independently_reaggregatable"] == "false", "summary-only primary is mislabeled")
        else:
            require(int(row["raw_records"]) == 600, "raw-retained execution record count differs")
            require(row["independently_reaggregatable"] == "true", "raw-retained execution is mislabeled")

    provenance = json.loads((D / "materializer_provenance.json").read_text(encoding="utf-8"))
    require(provenance["summary-only-primary"]["raw_source"] is None, "primary raw source must remain absent")
    require(provenance["summary-only-primary"]["independently_reaggregatable"] is False, "primary provenance is inaccurate")
    require(provenance["retained-clean"]["raw_records"] == 600, "clean provenance is incomplete")
    require(provenance["final-current"]["raw_records"] == 600, "final provenance is incomplete")

    topology = rows("topology_cases.csv")
    topology_summary = json.loads((D / "topology_summary.json").read_text(encoding="utf-8"))
    require(len(topology) == 2_550 and len({r["blocks"] for r in topology}) == 51, "topology matrix incomplete")
    keys = set()
    for row in topology:
        blocks = [set(map(int, block.split(","))) for block in row["blocks"].split("|")]
        central = int(row["central"])
        quorum = set(map(int, row["quorum"].split(",")))
        key = (row["blocks"], central, tuple(sorted(quorum)))
        require(key not in keys, "duplicate placement")
        keys.add(key)
        require(sorted(value for block in blocks for value in block) == list(range(5)) and len(quorum) == 3, "bad topology")
        central_count = sum(len(block) for block in blocks if central in block)
        quorum_count = sum(len(block) for block in blocks if len(block & quorum) >= 2)
        require(int(row["central_responding_sites"]) == central_count, "central reachability mismatch")
        require(int(row["quorum_responding_sites"]) == quorum_count, "quorum reachability mismatch")
    for role in ("central", "quorum"):
        mean = sum(Fraction(int(row[role + "_responding_sites"]), 5) for row in topology) / len(topology)
        require(str(mean) == topology_summary[role + "_mean"], "topology mean mismatch")

    print(
        "PASS: final-current and retained-clean raw timings independently reaggregated; "
        "the 3.03-fold primary execution is explicitly summary-only; 2550 topology placements checked"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS,
                        help="read-only result root containing tpds/ and reproduction.json")
    RESULTS = parser.parse_args().results_dir
    D = RESULTS / "tpds"
    main()
