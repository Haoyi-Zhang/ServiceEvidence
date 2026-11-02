#!/usr/bin/env python3
"""Compare deterministic result fields, excluding explicitly named measurements."""
from __future__ import annotations
import argparse
import csv
import gzip
import json
from pathlib import Path

MEASUREMENTS = frozenset({
    'seconds', 'reference_seconds', 'indexed_seconds', 'reference_over_indexed',
    'reference_median_ms', 'indexed_median_ms', 'paired_speedup_median',
    'paired_speedup_min', 'paired_speedup_max',
    'elapsed_seconds', 'cpu_seconds', 'peak_rss_mib', 'centralized_seconds',
    'rpc_median_ms', 'rpc_p95_ms', 'certificate_ms_median', 'certificate_ms_p95',
    'certificate_seconds', 'compaction_seconds', 'emulation_seconds',
    'generation_seconds', 'materialization_seconds', 'total_seconds',
    'generation_ms', 'verification_ms', 'generation_ms_median',
    'verification_ms_median', 'generation_ms_p95', 'verification_ms_p95',
    'median_generation_ms', 'median_verification_ms',
    'certificate_generation_median_ms', 'certificate_verification_ms',
    'certificate_verification_ms_median', 'elapsed_seconds_median',
    'rpc_p95_ms_median', 'elapsed_seconds_range', 'rpc_p95_ms_range',
    'certificate_verification_ms_range',
    # Raw workflow measurements: workflow_mws.py records these clocks and
    # phase/certificate latencies. Do not exclude counters, bytes or *_ns by
    # pattern: only the documented timing/CPU/RSS measurements are exceptions.
    'workflow_ns', 'process_cpu_ns', 'rpc_ns', 'checker_ns', 'reload_ns',
    'phases_including_checker_ns', 'certificate_ms',
})

def stable(value: object) -> object:
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in MEASUREMENTS}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value

def read(path: Path) -> object:
    compressed = path.suffix == '.gz'
    suffix = path.with_suffix('').suffix if compressed else path.suffix
    opener = gzip.open if compressed else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        if suffix == '.csv':
            return list(csv.DictReader(stream))
        if suffix == '.jsonl':
            return [json.loads(line) for line in stream]
        return json.load(stream)


def inventory(root: Path) -> dict[str, Path]:
    """Index logical evidence names, independent of lossless gzip packaging.

    Never silently choose between two representations of the same input.
    Reproduction receipts and runtime-environment captures retain the existing
    exclusions; scientific states, certificates and counts do not.
    """
    if not root.is_dir():
        raise ValueError(f'Not a result directory: {root}')
    files: dict[str, Path] = {}
    portable: set[str] = set()
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        logical = rel.with_suffix('') if rel.suffix == '.gz' else rel
        if logical.suffix not in {'.json', '.jsonl', '.csv'}:
            continue
        if logical.name in {'reproduction.json', 'reproduction.csv'} or 'runtime_environment' in rel.parts:
            continue
        name = logical.as_posix()
        if name.casefold() in portable:
            raise ValueError(f'Duplicate/ambiguous logical evidence input: {name}')
        files[name] = path
        portable.add(name.casefold())
    return files

def compare(reference: Path, candidate: Path) -> dict:
    expected, observed = inventory(reference), inventory(candidate)
    missing = sorted(expected.keys() - observed.keys())
    unexpected = sorted(observed.keys() - expected.keys())
    different = [name for name in sorted(expected.keys() & observed.keys())
                 if stable(read(expected[name])) != stable(read(observed[name]))]
    empty = [label for label, files in (('reference', expected), ('candidate', observed)) if not files]
    return {'compared_files': len(expected), 'missing_files': missing,
            'unexpected_files': unexpected, 'empty_evidence_roots': empty,
            'reference_inventory': sorted(expected), 'candidate_inventory': sorted(observed),
            'different_stable_files': different,
            'excluded_measurement_fields': sorted(MEASUREMENTS),
            'stable_results_equal': not empty and not missing and not unexpected and not different}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args()
    if not args.reference.is_dir() or not args.candidate.is_dir():
        parser.error('Both arguments must be result directories.')
    try:
        outcome = compare(args.reference, args.candidate)
    except (ValueError, OSError, EOFError) as error:
        parser.exit(1, f'FAIL: {error}\n')
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome['stable_results_equal'] else 1)
