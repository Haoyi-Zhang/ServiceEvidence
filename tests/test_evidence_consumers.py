"""Passive retained-input consumers; all mutations and output guards are owned.

Works in an artifact-only checkout. No service, campaign, compiler or network
is invoked. Subprocesses inherit the test runner's normal/optimized mode.
"""
from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('population_result_comparison', ROOT / 'scripts/compare_results.py')
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_data(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == '.gz' else open
    logical = path.with_suffix('') if path.suffix == '.gz' else path
    with opener(path, 'wt', encoding='utf-8', newline='') as stream:
        if logical.suffix == '.csv':
            writer = csv.DictWriter(stream, fieldnames=list(value[0]))
            writer.writeheader()
            writer.writerows(value)
        elif logical.suffix == '.jsonl':
            for row in value:
                stream.write(json.dumps(row) + '\n')
        else:
            json.dump(value, stream)


def snapshot(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*') if p.is_file()}


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)

    @staticmethod
    def command(script, *args):
        flags = ['-B', '-O'] if sys.flags.optimize else ['-B']
        return [sys.executable, *flags, str(ROOT / 'scripts' / script), *map(str, args)]

    def run_consumer(self, script, *args, guard=False, accept_output=False):
        command = self.command(script, *args)
        report = self.work / 'existing-derived-report.txt'
        if guard:
            report.write_bytes(b'original derived report\n')
            # A real consumer must succeed before a downstream report writer
            # may replace the existing output. Never redirect stdout onto it.
            writer = (
                'import pathlib,subprocess,sys\n'
                'try: subprocess.run(sys.argv[2:], check=True)\n'
                'except subprocess.CalledProcessError as error: sys.exit(error.returncode)\n'
                'pathlib.Path(sys.argv[1]).write_bytes(b"replacement report\\n")\n'
            )
            command = [sys.executable, '-B', *(['-O'] if sys.flags.optimize else []),
                       '-c', writer, str(report), *command]
        before = snapshot(self.work)
        result = subprocess.run(command, cwd=ROOT,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'},
            capture_output=True, text=True, encoding='utf-8', timeout=55)
        if guard:
            if accept_output:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(report.read_bytes(), b'replacement report\n')
                before.pop(report.name)
                after = snapshot(self.work); after.pop(report.name)
                self.assertEqual(before, after, 'consumer changed its inputs')
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(report.read_bytes(), b'original derived report\n')
                self.assertEqual(before, snapshot(self.work), 'failed read-only consumer changed inputs/output')
        return result

    def assert_pass(self, script, *args):
        result = self.run_consumer(script, *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def tpds_copy(self, name):
        result = self.work / name
        shutil.copytree(ROOT / 'results/tpds', result / 'tpds')
        shutil.copy2(ROOT / 'results/reproduction.json', result / 'reproduction.json')
        return result

    def mutex_copy(self, name):
        result = self.work / name
        result.mkdir()
        for path in (ROOT / 'results/primary-mws-20261014/pure-003').iterdir():
            if path.is_file() and path.suffix in {'.csv', '.json'}:
                shutil.copy2(path, result / path.name)
        return result


class ComparisonInventoryTests(ConsumerTests):
    def pair(self):
        ref, candidate = self.work / 'reference', self.work / 'candidate'
        ref.mkdir(); candidate.mkdir()
        return ref, candidate

    def test_genuine_current_retained_inventory_includes_compressed_records(self):
        result = self.assert_pass('compare_results.py', ROOT / 'results/current', ROOT / 'results/current')
        data = json.loads(result.stdout)
        self.assertTrue(data['stable_results_equal'])
        self.assertGreater(data['compared_files'], 0)
        self.assertIn('socket/generated-1/query_answers.json', data['reference_inventory'])
        self.assertIn('equal_work/authority-majority-seed-1/peer-evidence.json', data['reference_inventory'])

    def test_report_gate_can_publish_after_a_successful_real_consumer(self):
        ref, candidate = self.pair()
        for directory in (ref, candidate):
            write_data(directory / 'kept.json.gz', {'seed': 1})
        self.run_consumer('compare_results.py', ref, candidate, guard=True, accept_output=True)

    def test_missing_actual_compressed_query_evidence_fails_and_preserves_output(self):
        ref, candidate = self.pair()
        for directory in (ref, candidate):
            target = directory / 'socket/generated-1'
            target.mkdir(parents=True)
            shutil.copy2(ROOT / 'results/current/socket/generated-1/result.json', target / 'result.json')
        shutil.copy2(ROOT / 'results/current/socket/generated-1/query_answers.json.gz',
                     ref / 'socket/generated-1/query_answers.json.gz')
        result = self.run_consumer('compare_results.py', ref, candidate, guard=True)
        self.assertEqual(json.loads(result.stdout)['missing_files'], ['socket/generated-1/query_answers.json'])

    def test_lossless_packaging_matches_without_ignoring_documented_evidence(self):
        ref, candidate = self.pair()
        for suffix, value in (('json', {'cells': [], 'wire_bytes': 19}),
                              ('jsonl', [{'query': ['a', 'b']}, {'query': ['a', 'c']}]),
                              ('csv', [{'seed': '1', 'seconds': '2'}])):
            write_data(ref / ('evidence.' + suffix + '.gz'), value)
            write_data(candidate / ('evidence.' + suffix), value)
        data = json.loads(self.assert_pass('compare_results.py', ref, candidate).stdout)
        self.assertEqual(data['compared_files'], 3)
        self.assertEqual(data['reference_inventory'], data['candidate_inventory'])

    def test_only_explicit_measurement_names_are_excluded_in_compressed_records(self):
        ref, candidate = self.pair()
        first = {field: 1 for field in comparison.MEASUREMENTS}
        second = {field: 2 for field in comparison.MEASUREMENTS}
        first.update(phases_including_checker_ns={'query': 1}, certificate_ms=[1],
                     state={'cells': [{'vote': 'same'}]}, certificate={'kind': 'same'},
                     wire_bytes=10, event_count=2, undocumented_ns=3)
        second.update(phases_including_checker_ns={'query': 2}, certificate_ms=[2],
                      state=copy.deepcopy(first['state']), certificate={'kind': 'same'},
                      wire_bytes=10, event_count=2, undocumented_ns=3)
        write_data(ref / 'raw.json.gz', first)
        write_data(candidate / 'raw.json.gz', second)
        self.assert_pass('compare_results.py', ref, candidate)
        mutations = {
            'state': {'cells': [{'vote': 'different'}]},
            'certificate': {'kind': 'ambiguous'}, 'wire_bytes': 11,
            'event_count': 3, 'undocumented_ns': 4,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(second); changed[field] = value
                write_data(candidate / 'raw.json.gz', changed)
                result = self.run_consumer('compare_results.py', ref, candidate, guard=True)
                self.assertEqual(json.loads(result.stdout)['different_stable_files'], ['raw.json'])

    def test_empty_or_wrong_root_cannot_be_an_equal_evidence_set(self):
        ref, candidate = self.pair()
        result = self.run_consumer('compare_results.py', ref, candidate, guard=True)
        self.assertEqual(json.loads(result.stdout)['empty_evidence_roots'], ['reference', 'candidate'])
        write_data(ref / 'kept.json.gz', {'seed': 1})
        write_data(candidate / 'wrong.json.gz', {'seed': 1})
        result = self.run_consumer('compare_results.py', ref, candidate, guard=True)
        self.assertEqual(json.loads(result.stdout)['missing_files'], ['kept.json'])
        self.assertEqual(json.loads(result.stdout)['unexpected_files'], ['wrong.json'])

    def test_additional_input_is_not_silently_ignored(self):
        ref, candidate = self.pair()
        for directory in (ref, candidate):
            write_data(directory / 'kept.json.gz', {'seed': 1})
        write_data(candidate / 'extra.jsonl.gz', [{'seed': 2}])
        result = self.run_consumer('compare_results.py', ref, candidate, guard=True)
        self.assertEqual(json.loads(result.stdout)['unexpected_files'], ['extra.jsonl'])

    def test_duplicate_packaging_is_refused_on_either_side(self):
        ref, candidate = self.pair()
        for directory in (ref, candidate):
            write_data(directory / 'kept.json', {'seed': 1})
        for directory in (ref, candidate):
            with self.subTest(side=directory.name):
                duplicate = directory / 'kept.json.gz'
                write_data(duplicate, {'seed': 1})
                result = self.run_consumer('compare_results.py', ref, candidate, guard=True)
                self.assertIn('ambiguous logical evidence', result.stderr)
                duplicate.unlink()

    def test_corrupt_compressed_input_cannot_overwrite_report(self):
        ref, candidate = self.pair()
        write_data(ref / 'kept.json.gz', {'seed': 1})
        (candidate / 'kept.json.gz').write_bytes(b'not gzip')
        result = self.run_consumer('compare_results.py', ref, candidate, guard=True)
        self.assertIn('FAIL:', result.stderr)


class MaterializerPopulationTests(ConsumerTests):
    def test_genuine_retained_materializer_and_topology_pass(self):
        result = self.assert_pass('verify_tpds.py')
        self.assertIn('2550 topology placements checked', result.stdout)
        self.assertEqual(len(read_csv(ROOT / 'results/tpds/materializer_raw.csv')), 600)
        self.assertEqual(len(read_csv(ROOT / 'results/tpds/materializer_cases.csv')), 60)
        self.assertEqual(len(read_csv(ROOT / 'results/tpds/materializer_summary.csv')), 12)

    def test_original_seed_99_counterexample_fails_real_cli(self):
        result = self.tpds_copy('seed-counterexample')
        path = result / 'tpds/materializer_raw.csv'
        rows = read_csv(path)
        changed = 0
        for row in rows:
            if row['seed'] == '1':
                row['seed'] = '99'; changed += 1
        self.assertEqual(changed, 120)
        write_csv(path, rows)
        completed = self.run_consumer('verify_tpds.py', '--results-dir', result, guard=True)
        self.assertIn('materializer raw: incomplete or unexpected identity population', completed.stderr)

    def test_raw_population_rejects_missing_duplicate_and_wrong_dimensions(self):
        for mutation in ('missing', 'duplicate', 'family', 'handles', 'seed', 'implementation', 'repetition', 'infinite'):
            with self.subTest(mutation=mutation):
                result = self.tpds_copy('raw-' + mutation)
                path = result / 'tpds/materializer_raw.csv'
                rows = read_csv(path)
                if mutation == 'missing': rows.pop()
                elif mutation == 'duplicate': rows[0] = dict(rows[1])
                elif mutation == 'infinite': rows[0]['seconds'] = 'inf'
                else: rows[0][mutation] = 'unexpected'
                write_csv(path, rows)
                self.run_consumer('verify_tpds.py', '--results-dir', result, guard=True)

    def test_case_and_summary_rows_are_unique_complete_and_bound_to_raw(self):
        for surface, mutation in (('cases', 'duplicate'), ('cases', 'missing'), ('cases', 'seed'),
                                  ('cases', 'timing'), ('cases', 'repetitions'),
                                  ('summary', 'duplicate'), ('summary', 'missing'), ('summary', 'cases')):
            with self.subTest(surface=surface, mutation=mutation):
                result = self.tpds_copy(surface + '-' + mutation)
                path = result / ('tpds/materializer_' + surface + '.csv')
                rows = read_csv(path)
                if mutation == 'missing': rows.pop()
                elif mutation == 'duplicate': rows[0] = dict(rows[1])
                elif mutation == 'timing': rows[0]['reference_seconds'] = str(float(rows[0]['reference_seconds']) * 2)
                else: rows[0][mutation] = '99'
                write_csv(path, rows)
                self.run_consumer('verify_tpds.py', '--results-dir', result, guard=True)

    def test_clean_retained_raw_is_checked_against_the_same_declared_population(self):
        result = self.tpds_copy('clean-wrong-seed')
        path = result / 'reproduction.json'
        document = json.loads(path.read_text(encoding='utf-8'))
        for row in document['timing_replication']['clean_raw_timings']:
            if row['seed'] == '1': row['seed'] = '99'
        path.write_text(json.dumps(document), encoding='utf-8')
        self.run_consumer('verify_tpds.py', '--results-dir', result, guard=True)

    def test_replication_and_summary_only_identities_cannot_hide_missing_rows(self):
        for mutation in ('replication-duplicate', 'replication-missing', 'replication-count', 'primary-duplicate'):
            with self.subTest(mutation=mutation):
                result = self.tpds_copy(mutation)
                if mutation == 'primary-duplicate':
                    path = result / 'reproduction.json'
                    document = json.loads(path.read_text(encoding='utf-8'))
                    rows = document['timing_replication']['primary_summary']
                    rows[0] = dict(rows[1])
                    path.write_text(json.dumps(document), encoding='utf-8')
                else:
                    path = result / 'tpds/materializer_replications.csv'
                    rows = read_csv(path)
                    if mutation == 'replication-missing': rows.pop()
                    elif mutation == 'replication-duplicate': rows[0] = dict(rows[1])
                    else: rows[0]['cases'] = '99'
                    write_csv(path, rows)
                self.run_consumer('verify_tpds.py', '--results-dir', result, guard=True)

    def test_new_valid_measurements_are_not_hardcoded_to_retained_values(self):
        result = self.tpds_copy('new-measurements')
        for filename, fields in (
            ('materializer_raw.csv', ('seconds',)),
            ('materializer_cases.csv', ('reference_seconds', 'indexed_seconds')),
            ('materializer_summary.csv', ('reference_median_ms', 'indexed_median_ms')),
            ('materializer_replications.csv', ('reference_median_ms', 'indexed_median_ms')),
        ):
            path = result / 'tpds' / filename
            rows = read_csv(path)
            for row in rows:
                if filename == 'materializer_replications.csv' and row['execution'] != 'final-current':
                    continue
                for field in fields: row[field] = str(2 * float(row[field]))
            write_csv(path, rows)
        self.assert_pass('verify_tpds.py', '--results-dir', result)


class MutexPopulationTests(ConsumerTests):
    def test_genuine_retained_mutex_cohorts_pass_without_remeasurement(self):
        for relative in ('mutex', 'primary-mws-20261014/pure-001',
                         'primary-mws-20261014/pure-002', 'primary-mws-20261014/pure-003'):
            with self.subTest(cohort=relative):
                result = self.assert_pass('verify_mutex.py', '--out', ROOT / 'results' / relative)
                self.assertIn('900 raw calls/60 cases/12 summaries reaggregated', result.stdout)

    def test_original_unchanged_medians_duplicate_case_fails_real_cli(self):
        result = self.mutex_copy('duplicate-case')
        path = result / 'stress_cases.csv'
        rows = read_csv(path)
        before_summary = (result / 'stress_summary.csv').read_bytes()
        donor = next(row for row in rows if (row['family'], row['handles'], row['seed']) == ('sparse_cut', '128', '1'))
        target = next(i for i, row in enumerate(rows)
                      if (row['family'], row['handles'], row['seed']) == ('sparse_cut', '128', '2'))
        rows[target] = dict(donor)
        self.assertEqual(len({(r['family'], r['handles'], r['seed']) for r in rows}), 59)
        write_csv(path, rows)
        completed = self.run_consumer('verify_mutex.py', '--out', result, guard=True)
        self.assertIn('stress cases: duplicate identity', completed.stderr)
        self.assertEqual((result / 'stress_summary.csv').read_bytes(), before_summary)

    def test_raw_case_and_summary_population_mutations_all_fail(self):
        mutations = (
            ('raw', 'duplicate'), ('raw', 'missing'), ('raw', 'seed'),
            ('raw', 'family'), ('raw', 'handles'), ('raw', 'implementation'), ('raw', 'repetition'),
            ('cases', 'missing'), ('cases', 'seed'), ('cases', 'timing'),
            ('summary', 'duplicate'), ('summary', 'missing'), ('summary', 'seeds'), ('summary', 'repetitions'),
        )
        for surface, mutation in mutations:
            with self.subTest(surface=surface, mutation=mutation):
                result = self.mutex_copy(surface + '-' + mutation)
                path = result / ('stress_' + surface + '.csv')
                rows = read_csv(path)
                if mutation == 'missing': rows.pop()
                elif mutation == 'duplicate': rows[0] = dict(rows[1])
                elif mutation == 'timing': rows[0]['indexed_median_ms'] = str(2 * float(rows[0]['indexed_median_ms']))
                else: rows[0][mutation] = '99'
                write_csv(path, rows)
                self.run_consumer('verify_mutex.py', '--out', result, guard=True)

    def test_consistently_relabelled_raw_and_cases_still_reject_foreign_seed(self):
        result = self.mutex_copy('foreign-seed')
        for name in ('stress_raw.csv', 'stress_cases.csv'):
            path = result / name
            rows = read_csv(path)
            for row in rows:
                if row['seed'] == '1': row['seed'] = '99'
            write_csv(path, rows)
        self.run_consumer('verify_mutex.py', '--out', result, guard=True)

    def test_new_valid_measurements_do_not_change_population_or_predicates(self):
        result = self.mutex_copy('new-measurements')
        for filename, fields in (
            ('stress_raw.csv', ('seconds',)),
            ('stress_cases.csv', ('scanning_median_ms', 'indexed_median_ms', 'mws_edge_ids_median_ms')),
            ('stress_summary.csv', ('scanning_median_ms', 'indexed_median_ms', 'mws_edge_ids_median_ms')),
        ):
            path = result / filename
            rows = read_csv(path)
            for row in rows:
                for field in fields: row[field] = str(2 * float(row[field]))
            write_csv(path, rows)
        self.assert_pass('verify_mutex.py', '--out', result)


if __name__ == '__main__':
    unittest.main()
