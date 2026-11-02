"""Passive recorded evidence and tiny public-verifier root regressions."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_persistence_cutpoints as cuts
from unpack_process_cutpoints import unpack
spec=importlib.util.spec_from_file_location('receiving_certificate_checker',ROOT/'checker/verify.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)

class ReceivingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.records=Path(cls.tmp.name)/'records'
        unpack(ROOT/'results/process-cutpoints-evidence.zip',cls.records,
               '3f16b3ad626888137c97418a341e1eb73356664a581530c2240f104531a52fbe')
        cls.directory=cls.records/'case-017'
        cls.record=json.loads((cls.directory/'record.json').read_text())

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_full_59_original_cases_and_measured_preimage(self):
        result=cuts.verify(self.records)
        self.assertEqual((result['cases'],result['supervised_kills']),(59,54))
        self.assertTrue(result['measured_source_bindings_verified'])
        self.assertEqual(result['measured_sources_differ_from_current'],['src/cie/service.py'])
        self.assertFalse(result['current_source_campaign_claimed'])

    def test_incomplete_or_aliased_acknowledgements_are_refused(self):
        for mutation in ('epoch-bool','threshold-bool','accepted-int','vector-float','missing-seed-result',
                         'missing-ingest-result','missing-member','missing-floors','wrong-member','wrong-floor',
                         'state-cell-missing','vector-source-missing'):
            row=copy.deepcopy(self.record)
            recovered=cuts.one_event(row['recovery'],'RECOVER')
            if mutation=='epoch-bool':recovered['state']['cells'][0]['epoch']=False
            elif mutation=='threshold-bool':recovered['state']['threshold']=True
            elif mutation=='accepted-int':recovered['floor']['accepted']=1
            elif mutation=='vector-float':recovered['floor']['result']['vectors'][0]['epoch']=1.0
            elif mutation=='missing-seed-result':cuts.one_event(row['seed'],'ACK').pop('result')
            elif mutation=='missing-ingest-result':cuts.one_event(row['attempt'],'ACK').pop('result')
            elif mutation=='missing-member':recovered['floor']['result'].pop('member')
            elif mutation=='missing-floors':recovered['floor']['result'].pop('floors')
            elif mutation=='wrong-member':recovered['floor']['result']['member']='wrong'
            elif mutation=='wrong-floor':recovered['floor']['result']['floors']=[['a','b',999]]
            elif mutation=='state-cell-missing':recovered['state']['cells'].pop()
            elif mutation=='vector-source-missing':recovered['floor']['result']['vectors'].pop()
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):cuts.verify_case(row,self.directory)

    def test_source_inventory_and_captured_bytes_are_not_optional(self):
        for bad in ({},dict(cuts.RECORDED_SOURCES,**{'cie/service.py':'0'*64})):
            with self.assertRaises(ValueError):cuts.verify_source_bindings(bad)
        original=Path.read_bytes
        with patch.object(Path,'read_bytes',lambda p:b'bad' if 'process-cutpoints-source-preimage' in p.parts else original(p)),self.assertRaises(ValueError):
            cuts.verify_source_bindings(dict(cuts.RECORDED_SOURCES))

    def test_non_object_roots_are_typed_library_and_cli_errors(self):
        state=json.loads((ROOT/'results/example_state.json').read_text())
        cert=json.loads((ROOT/'results/example_same_certificate.json').read_text())
        for bad in ([],None,True,0,'owned'):
            for s,c in ((bad,cert),(state,bad)):
                with self.subTest(bad=bad),self.assertRaises(checker.VerificationError):checker.verify(s,c)
                with tempfile.TemporaryDirectory() as tmp:
                    sp,cp=Path(tmp)/'state.json',Path(tmp)/'certificate.json'
                    sp.write_text(json.dumps(s),encoding='utf-8');cp.write_text(json.dumps(c),encoding='utf-8')
                    result=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'checker/verify.py'),str(sp),str(cp)],capture_output=True,text=True,encoding='utf-8',timeout=30)
                    self.assertEqual(result.returncode,1);self.assertIn('FAIL:',result.stderr);self.assertNotIn('Traceback',result.stderr)

    def test_all_three_retained_certificate_kinds_stay_valid_without_mutation(self):
        state=json.loads((ROOT/'results/example_state.json').read_text())
        for kind in ('same','different','ambiguous'):
            cert=json.loads((ROOT/f'results/example_{kind}_certificate.json').read_text())
            before=copy.deepcopy((state,cert));checker.verify(state,cert);self.assertEqual(before,(state,cert))

if __name__=='__main__':unittest.main()
