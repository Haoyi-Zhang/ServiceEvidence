"""Owned bounded-search admission and strict nested JSON regressions."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import cie.model as model
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ambiguity_contract_checker',ROOT/'checker/verify.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)

def family(n=2):
    cs=[f'c{i:03}' for i in range(n)];ds=[f'd{i:03}' for i in range(n)]
    r=model.Replica('bounded',['s0','s1','s2','s3','s4'],2,['a','b',*cs,*ds,'z'])
    def edge(a,b,cost):
        for i,s in enumerate(r.sources):
            r.add(model.EvidenceCell(*sorted((a,b)),0,s,model.Vote.SAME if cost==1 and i==0 else model.Vote.UNKNOWN,'owned'))
    edge('a','b',1);edge('b','z',1)
    for c in cs:
        edge('a',c,2)
        for d in ds:edge(c,d,1)
    return r

class AmbiguityContractTests(unittest.TestCase):
    def test_lazy_search_matches_recursive_admission_budget(self):
        r=family();state=copy.deepcopy(r.export_state())
        with patch.object(model,'MAX_AMBIGUITY_CANDIDATES',6),patch.object(checker,'MAX_AMBIGUITY_CANDIDATES',6):
            c=r.certificate('a','z')
            self.assertEqual((c['authorization_gap'],c['edge_count']),(2,2))
            checker.verify(state,c)
        with patch.object(model,'MAX_AMBIGUITY_CANDIDATES',5),patch.object(checker,'MAX_AMBIGUITY_CANDIDATES',5):
            with self.assertRaises(ValueError):r.certificate('a','z')
            with self.assertRaises(checker.VerificationError):checker.verify(state,c)
        self.assertEqual(r.export_state(),state)

    def test_nested_bool_numeric_aliases_refuse(self):
        r=family();state=r.export_state();c=r.certificate('a','z')
        variants=[]
        bad=copy.deepcopy(c);bad['component_path'][0]=False;variants.append(bad)
        for field in ('observed','sealed'):
            bad=copy.deepcopy(c);bad['steps'][0][field]=int(bad['steps'][0][field]);variants.append(bad)
        for field in ('from_component','authorization_gap','epoch'):
            bad=copy.deepcopy(c);bad['steps'][0][field]=float(bad['steps'][0][field]);variants.append(bad)
        for bad in variants:
            with self.assertRaises(checker.VerificationError):checker.verify(state,bad)
        checker.verify(state,c)

    def test_moderate_family_under_default_budget(self):
        r=family(16);c=r.certificate('a','z');checker.verify(r.export_state(),c)
        self.assertEqual((c['authorization_gap'],c['edge_count']),(2,2))

if __name__=='__main__':unittest.main()
