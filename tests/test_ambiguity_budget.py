"""Exact certificates fail closed at declared owned-search resource limits."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from cie.model import EvidenceCell, Replica, Vote
import cie.model as model

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('budget_checker', ROOT / 'checker/verify.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def replica(count=5, handles='abcd'):
    return Replica('owned-budget', tuple(f's{i}' for i in range(count)), 2, handles)


def vector(r, edge, votes):
    for source, vote in zip(r.sources, votes):
        r.add(EvidenceCell(*edge, 0, source, Vote(vote), 'owned budget fixture'))


class AmbiguityBudgetTests(unittest.TestCase):
    def test_source_cap_refuses_both_search_implementations(self):
        r = replica(6)
        state = r.export_state()
        with self.assertRaisesRegex(ValueError, 'source limit exceeded'):
            r.certificate('a', 'd')
        with self.assertRaisesRegex(checker.VerificationError, 'source limit exceeded'):
            checker.minimal_ambiguity(checker.validate_state(state), 'a', 'd')
        self.assertEqual(r.export_state(), state)

    def test_five_source_direct_fallback_is_exact(self):
        r = replica()
        cert = r.certificate('a', 'd')
        self.assertEqual((cert['authorization_gap'], cert['edge_count']), (5, 1))
        checker.verify(r.export_state(), cert)

    def test_budget_refusal_returns_no_approximation_or_mutation(self):
        r = replica()
        state = r.export_state()
        cert = r.certificate('a', 'd')
        with patch.object(model, 'MAX_AMBIGUITY_CANDIDATES', 0):
            with self.assertRaisesRegex(ValueError, 'search budget exceeded'):
                r.certificate('a', 'd')
        with patch.object(checker, 'MAX_AMBIGUITY_CANDIDATES', 0):
            with self.assertRaisesRegex(checker.VerificationError, 'search budget exceeded'):
                checker.verify(state, cert)
        self.assertEqual(r.export_state(), state)

    def test_compatible_three_edge_optimum_is_unchanged(self):
        r = replica()
        for edge in (('a', 'b'), ('b', 'c'), ('c', 'd')):
            vector(r, edge, ('same',) + ('unknown',) * 4)
        cert = r.certificate('a', 'd')
        self.assertEqual((cert['authorization_gap'], cert['edge_count']), (3, 3))
        checker.verify(r.export_state(), cert)

    def test_cap_is_not_applied_to_polynomial_same_or_different_queries(self):
        r = replica(6)
        vector(r, ('a', 'b'), ('same', 'same') + ('unknown',) * 4)
        vector(r, ('c', 'd'), ('different',) + ('unknown',) * 5)
        for edge, kind in ((('a', 'b'), 'same'), (('c', 'd'), 'different')):
            cert = r.certificate(*edge)
            self.assertEqual(cert['kind'], kind)
            checker.verify(r.export_state(), cert)

    def test_default_budget_stops_a_dense_owned_unreachable_search(self):
        handles = tuple(f'h{i:02}' for i in range(26)) + ('z',)
        r = replica(handles=handles)
        for index, left in enumerate(handles[:-1]):
            for right in handles[index + 1:-1]:
                vector(r, (left, right), ('same',) + ('unknown',) * 4)
        before = r.export_state()
        with self.assertRaisesRegex(ValueError, 'search budget exceeded'):
            r.certificate(handles[0], 'z')
        with self.assertRaisesRegex(checker.VerificationError, 'search budget exceeded'):
            checker.minimal_ambiguity(checker.validate_state(before), handles[0], 'z')
        self.assertEqual(r.export_state(), before)
