"""Owned JSON vote-shape regressions; rejection is not an acceptance repair."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cie.model import EvidenceCell, Replica, Vote
from cie.service import compact_certificate

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('vote_type_checker', ROOT / 'checker/verify.py')
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
MALFORMED = ([], {}, None, 0, 1.5, True, '', 'unsupported')


def fixture(vote=Vote.SAME):
    replica = Replica('owned', ['s'], 1, ['a', 'b'])
    replica.add(EvidenceCell('a', 'b', 0, 's', vote, 'owned benign vote-shape fixture'))
    return replica.export_state(), replica.certificate('a', 'b')


def malformed(value, surface):
    state, certificate = fixture(Vote.DIFFERENT if surface == 'different_cell' else Vote.SAME)
    raw = (state['cells'][0] if surface == 'state_cell' else certificate['cell']
           if surface == 'different_cell' else certificate['support'][0]['cells'][0])
    raw['vote'] = value
    return state, certificate, raw


class CheckerVoteTypeTests(unittest.TestCase):
    def test_state_votes_reject_all_malformed_shapes_consistently(self):
        for value in MALFORMED:
            for entry in (checker.validate_state, lambda s: checker.verify(s, fixture()[1])):
                with self.subTest(value=value, entry=entry):
                    state, _, _ = malformed(value, 'state_cell')
                    with self.assertRaisesRegex(checker.VerificationError, 'invalid vote'):
                        entry(state)

    def test_full_certificate_votes_reject_all_malformed_shapes_consistently(self):
        for value in MALFORMED:
            for surface in ('same_cell', 'different_cell'):
                with self.subTest(value=value, surface=surface):
                    state, certificate, cell = malformed(value, surface)
                    with self.assertRaisesRegex(checker.VerificationError, 'vote is invalid'):
                        checker.canonical_cell(cell)
                    with self.assertRaisesRegex(checker.VerificationError, 'vote is invalid'):
                        checker.verify(state, certificate)

    def test_cli_keeps_rejecting_malformed_votes(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path, certificate_path = [Path(directory) / name for name in ('state.json', 'certificate.json')]
            for value in MALFORMED:
                for surface in ('state_cell', 'same_cell', 'different_cell'):
                    with self.subTest(value=value, surface=surface):
                        state, certificate, _ = malformed(value, surface)
                        state_path.write_text(json.dumps(state), encoding='utf-8')
                        certificate_path.write_text(json.dumps(certificate), encoding='utf-8')
                        command = [sys.executable, '-B'] + (['-O'] if sys.flags.optimize else [])
                        command += [str(ROOT / 'checker/verify.py'), str(state_path), str(certificate_path)]
                        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
                        self.assertEqual(result.returncode, 1)
                        self.assertEqual(result.stdout, '')
                        self.assertIn('FAIL:', result.stderr)
                        self.assertNotIn('Traceback', result.stderr)

    def test_legal_votes_full_and_key_certificates_are_unchanged(self):
        for vote, kind in ((Vote.SAME, 'same'), (Vote.DIFFERENT, 'different'), (Vote.UNKNOWN, 'ambiguous')):
            state, certificate = fixture(vote)
            saved = copy.deepcopy((state, certificate))
            self.assertEqual(certificate['kind'], kind)
            self.assertIsNone(checker.verify(state, certificate))
            self.assertIsNone(checker.verify(state, compact_certificate(certificate)))
            self.assertEqual((state, certificate), saved)
            self.assertEqual(checker.canonical_cell(state['cells'][0])[4], vote.value)

    def test_retained_legal_certificate_records_stay_readable(self):
        state = json.loads((ROOT / 'results/example_state.json').read_text(encoding='utf-8'))
        before = copy.deepcopy(state)
        for kind in ('same', 'different', 'ambiguous'):
            certificate = json.loads((ROOT / f'results/example_{kind}_certificate.json').read_text(encoding='utf-8'))
            self.assertIsNone(checker.verify(state, certificate))
            self.assertIsNone(checker.verify(state, compact_certificate(certificate)))
        self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
