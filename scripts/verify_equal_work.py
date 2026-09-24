#!/usr/bin/env python3
"""Verify paired central/quorum/peer result surfaces and certificates."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
spec = importlib.util.spec_from_file_location("equal_work_checker", ROOT / "checker" / "verify.py")
checker = importlib.util.module_from_spec(spec)
if spec.loader is None:
    raise RuntimeError("could not load checker")
spec.loader.exec_module(checker)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    with (RESULTS / "equal_work.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 30, "equal-work comparison must contain 30 paired rows")
    architectures = {"peer-evidence", "central-recompute", "coordinated-quorum"}
    layouts = {"authority-minority", "authority-majority"}
    require({row["architecture"] for row in rows} == architectures, "architecture set changed")
    require({row["layout"] for row in rows} == layouts, "partition layout set changed")
    require({int(row["seed"]) for row in rows} == set(range(1, 6)), "seed set changed")
    require(
        len({(row["architecture"], row["layout"], row["seed"]) for row in rows}) == 30,
        "paired comparison contains a duplicate or missing tuple",
    )

    expected_mean_availability = {
        "peer-evidence": 1.0,
        "central-recompute": 0.5,
        "coordinated-quorum": 0.6,
    }
    expected_case_availability = {
        ("peer-evidence", "authority-minority"): 1.0,
        ("peer-evidence", "authority-majority"): 1.0,
        ("central-recompute", "authority-minority"): 0.4,
        ("central-recompute", "authority-majority"): 0.6,
        ("coordinated-quorum", "authority-minority"): 0.6,
        ("coordinated-quorum", "authority-majority"): 0.6,
    }
    verified = 0
    for row in rows:
        architecture = row["architecture"]
        expected_case = expected_case_availability[(architecture, row["layout"])]
        require(float(row["partition_write_availability"]) == expected_case, "write availability changed")
        require(float(row["partition_query_availability"]) == expected_case, "query availability changed")
        require(int(row["partition_same"]) == 0, "partial closure authorized SAME")
        require(int(row["partition_different"]) == 0, "partial closure authorized DIFFERENT")
        require(row["final_kind"] == "same", "final query did not become SAME")
        require(int(row["final_false_merge_pairs"]) == 0, "final comparison has a false merge")
        require(int(row["final_false_split_pairs"]) == 0, "final comparison has a false split")
        require(int(row["restart_recovered"]) == 1, "restart did not recover")
        require(int(row["input_cells"]) == 2_200 and int(row["services"]) == 100, "frozen workload dimensions changed")
        require(int(row["requests"]) <= 5_000, "request cap exceeded")
        require(int(row["wire_bytes"]) <= 100 * 1024**2, "wire cap exceeded")
        require(float(row["elapsed_seconds"]) < 120.0, "case timeout exceeded")
        require(int(row["persistence_fsyncs"]) > 0, "persistence work was not counted")
        require(int(row["persistence_bytes_written"]) > 0, "persistence bytes were not counted")

        detail_path = (
            RESULTS
            / "equal_work"
            / f"{row['layout']}-seed-{row['seed']}"
            / f"{architecture}.json"
        )
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        final_answer = detail["detail"]["final_answer"]
        checker.verify(final_answer["state"], final_answer["certificate"])
        require(final_answer["certificate"]["kind"] == "same", "detail final certificate changed")
        verified += 1
        available = 0
        for answer in detail["detail"]["partition_answers"]:
            if answer is None:
                continue
            checker.verify(answer["state"], answer["certificate"])
            require(answer["certificate"]["kind"] == "ambiguous", "partial answer was not ambiguous")
            available += 1
            verified += 1
        require(available == int(row["partition_query_acks"]), "detail availability count changed")

    summary = json.loads((RESULTS / "equal_work_summary.json").read_text(encoding="utf-8"))
    require(summary["cases"] == 30, "summary case count changed")
    for architecture, availability in expected_mean_availability.items():
        item = summary["architectures"][architecture]
        require(item["cases"] == 10, "summary architecture count changed")
        require(item["partition_write_availability_mean"] == availability, "summary write availability changed")
        require(item["partition_query_availability_mean"] == availability, "summary query availability changed")
        require(item["partition_same_total"] == 0, "summary records a partial SAME answer")
        require(item["all_final_same"] is True, "summary final decision predicate failed")
        require(item["all_zero_false_merge"] is True and item["all_zero_false_split"] is True, "summary correctness predicate failed")
        require(item["all_restart_recovered"] is True, "summary restart predicate failed")

    print(f"PASS: 30 equal-work rows; {verified} state-coupled certificates; persistence, availability, and caps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
