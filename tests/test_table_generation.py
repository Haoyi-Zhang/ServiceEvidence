"""Table consumers preserve delivered style and read changed owned records."""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import render_evidence_tables as evidence
import render_tpds_assets as assets
from equal_work_data import aggregate, read_rows

MIB = 1024 ** 2


def rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def write_rows(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


class TableGenerationTests(unittest.TestCase):
    def assert_style(self, text, label, columns, caption):
        self.assertIn(r'\footnotesize', text)
        self.assertNotIn(r'\scriptsize', text)
        self.assertIn(r'\setlength{\tabcolsep}{3.5pt}', text)
        self.assertIn(r'\label{' + label + '}', text)
        self.assertIn(r'\begin{tabular}{' + columns + '}', text)
        self.assertIn(r'\caption{' + caption + '}', text)

    def test_public_neutral_records_keep_style_and_semantics(self):
        data = json.loads((ROOT / 'results/public_target_summary.json').read_text(encoding='utf-8'))
        selected, control = data['predicates']
        text = evidence.public_table()
        self.assert_style(text, 'tab:public-target', 'lrrrrr',
                          f"Public target-equivalence results over {selected['pairs']} probe/control pairs.")
        for label, row in (('Two-signal', selected), ('Closed-world endpoint', control)):
            self.assertIn(f"{label} & {row['predicted_same']} & {row['predicted_different']} & "
                          f"{row['predicted_unknown']} & {row['false_same'] + row['false_different']} & "
                          f"{100 * row['coverage']:.1f}\\%", text)
        self.assertIn(r'Coverage\\', text)

    def test_public_reads_changed_owned_result_record(self):
        data = json.loads((ROOT / 'results/public_target_summary.json').read_text(encoding='utf-8'))
        row = data['predicates'][0]
        row.update(predicted_same=7, predicted_different=19, predicted_unknown=250,
                   false_same=1, false_different=2, coverage=26 / row['pairs'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'public_target_summary.json').write_text(json.dumps(data), encoding='utf-8')
            with patch.object(evidence, 'RESULTS', path):
                text = evidence.public_table()
        self.assertIn(r'Two-signal & 7 & 19 & 250 & 3 & 9.4\%', text)

    def render_ranges(self, records):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_rows(path / 'equal_work.csv', records)
            data = aggregate(read_rows(path / 'equal_work.csv'))
            assets.render_equal_ranges(path / 'ranges.tex', data)
            return (path / 'ranges.tex').read_text(encoding='utf-8')

    def test_equal_ranges_neutral_records_keep_style_and_units(self):
        text = self.render_ranges(rows(ROOT / 'results/equal_work.csv'))
        self.assert_style(text, 'tab:equal-work-ranges', 'lrrrr',
                          'Equal-work ranges (ten cases/architecture). Responses: percentages at two measured cuts; bytes: MiB.')
        data = aggregate(read_rows(ROOT / 'results/equal_work.csv'))
        for key, label in (('central-recompute', 'Central'), ('coordinated-quorum', 'Quorum'), ('peer-evidence', 'Peer')):
            item = data[key]
            availability = '/'.join(f"{100 * item['partition_availability_by_layout'][layout]:.0f}"
                                    for layout in ('authority-minority', 'authority-majority'))
            ranges = [f"{item[field + '_range']['min'] / divisor:.2f}--{item[field + '_range']['max'] / divisor:.2f}"
                      for field, divisor in (('wire_bytes', MIB), ('persistence_bytes_written', MIB), ('elapsed_seconds', 1))]
            self.assertIn(' & '.join([label, availability + r'\%', *ranges]), text)

    def test_equal_ranges_follow_changed_raw_availability_bytes_and_time(self):
        records = rows(ROOT / 'results/equal_work.csv')
        for row in records:
            if row['architecture'] == 'central-recompute':
                row['partition_query_availability'] = '0.2' if row['layout'] == 'authority-minority' else '0.8'
                row['wire_bytes'] = str(2 * MIB)
                row['persistence_bytes_written'] = str(3 * MIB)
                row['elapsed_seconds'] = '4.5'
        text = self.render_ranges(records)
        self.assertIn(r'Central & 20/80\% & 2.00--2.00 & 3.00--3.00 & 4.50--4.50', text)

    def render_provenance(self, records):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_rows(path / 'tpds/materializer_replications.csv', records)
            provenance = json.loads((ROOT / 'results/tpds/materializer_provenance.json').read_text(encoding='utf-8'))
            (path / 'tpds/materializer_provenance.json').write_text(json.dumps(provenance), encoding='utf-8')
            with patch.object(assets, 'RESULTS', path):
                returned = assets.render_materializer_provenance(path / 'table.tex')
            self.assertEqual(returned, provenance)
            return (path / 'table.tex').read_text(encoding='utf-8')

    def test_materializer_neutral_records_keep_style_and_ratio_meaning(self):
        records = rows(ROOT / 'results/tpds/materializer_replications.csv')
        text = self.render_provenance(records)
        self.assert_style(text, 'tab:materializer-provenance', 'lrrrr',
                          '512-handle median reference/indexed speedups; summary-only lacks raw calls for independent reaggregation.')
        lookup = {(row['execution'], row['family']): row for row in records}
        for key, label in (('final-current', 'Raw-retained A'), ('retained-clean', 'Raw-retained B'), ('summary-only-primary', 'Summary only')):
            values = [f"{float(lookup[key, family]['paired_speedup_median']):.2f}"
                      for family in ('sparse_cut', 'dense_cut', 'low_conflict')]
            raw = int(lookup[key, 'sparse_cut']['raw_records'])
            self.assertIn(' & '.join([label, *values, str(raw) if raw else 'none']), text)

    def test_materializer_follows_changed_owned_replication_records(self):
        records = rows(ROOT / 'results/tpds/materializer_replications.csv')
        for row in records:
            if row['execution'] == 'final-current':
                row['paired_speedup_median'] = {'sparse_cut': '1.234', 'dense_cut': '0.875', 'low_conflict': '2.345'}[row['family']]
                row['raw_records'] = '610'
        self.assertIn('Raw-retained A & 1.23 & 0.88 & 2.35 & 610', self.render_provenance(records))


if __name__ == '__main__':
    unittest.main()
