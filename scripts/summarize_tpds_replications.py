#!/usr/bin/env python3
"""Combine two retained timing replications with the current TPDS execution."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = RESULTS / "tpds" / "materializer_replications.csv"
FIELDS = [
    "execution", "family", "handles", "cases", "reference_median_ms",
    "indexed_median_ms", "paired_speedup_median", "paired_speedup_min",
    "paired_speedup_max",
]


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def select(rows, execution):
    selected = []
    for row in rows:
        if int(row["handles"]) != 512:
            continue
        selected.append({"execution": execution, **{k: row[k] for k in FIELDS if k != "execution"}})
    return selected


def main():
    retained = json.loads((RESULTS / "reproduction.json").read_text(encoding="utf-8"))["timing_replication"]
    rows = []
    rows += select(retained["primary_summary"], "retained-primary")
    rows += select(retained["clean_summary"], "retained-clean")
    rows += select(read_csv(RESULTS / "tpds" / "materializer_summary.csv"), "final-current")
    if len(rows) != 9:
        raise ValueError("expected three executions by three families at 512 handles")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} replication summary rows to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
