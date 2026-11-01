"""Passive consumers and mutation refusals over the actual process-cut record.

No process termination, service invocation, source imports or benchmark rerun.
Explicitly separate from the historical automatically discovered test suite.
"""
import copy,importlib.util,json,os
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('passive_cutpoint_verifier',ROOT/'scripts/verify_persistence_cutpoints.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
RECORDS=Path(os.environ.get('CIE_PROCESS_CUT_RECORDS',ROOT/'results/process-cutpoints-native-20261101'))

class ProcessCutpointRecords(unittest.TestCase):
    def load(self,*,operation=None,cut=None,initial=None):
        for directory in sorted(RECORDS.glob('case-*')):
            row=json.loads((directory/'record.json').read_text())
            if (operation is None or row['operation']==operation) and (cut is None or row['cut']==cut) and (initial is None or row['initial']==initial):return row,directory
        self.fail('Required actual case missing; do not synthesize or skip')

    def test_complete_actual_matrix_and_raw_bytes(self):
        result=verifier.verify(RECORDS)
        self.assertEqual((result['cases'],result['supervised_kills'],result['native_partial_temporary_observations']),(59,54,6))
        self.assertEqual(result['successful_operation_acknowledgements'],6)

    def test_lost_previously_acknowledged_evidence_is_rejected(self):
        row,directory=self.load(operation='ingest',cut='after_dispatch_ack',initial='accepted0')
        row=copy.deepcopy(row)
        state=verifier.one_event(row['recovery'],'RECOVER')['state'];state['cells'].pop(0)
        with self.assertRaises(ValueError):verifier.verify_case(row,directory)

    def test_a_pre_return_ack_cannot_be_invented(self):
        row,directory=self.load(operation='ingest',cut='before_file_fsync')
        success,_=self.load(operation='ingest',cut='after_dispatch_ack')
        row=copy.deepcopy(row);row['attempt']['events'].append(copy.deepcopy(verifier.one_event(success['attempt'],'ACK')))
        with self.assertRaisesRegex(ValueError,'pre-return'):verifier.verify_case(row,directory)

    def test_orderly_exit_is_not_a_SIGKILL(self):
        row,directory=self.load(cut='after_replace')
        row=copy.deepcopy(row);row['attempt']['returncode']=0
        with self.assertRaisesRegex(ValueError,'SIGKILL'):verifier.verify_case(row,directory)

    def test_unsealed_floor_false_ack_is_rejected(self):
        row,directory=self.load(operation='unsealed_floor_vector')
        row=copy.deepcopy(row);verifier.one_event(row['recovery'],'RECOVER')['floor']['accepted']=True
        with self.assertRaisesRegex(ValueError,'floor'):verifier.verify_case(row,directory)

    def test_partial_file_byte_receipt_cannot_be_resealed(self):
        row,directory=self.load(cut='mid_write_prefix_flushed')
        row=copy.deepcopy(row);row['pending_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'binding'):verifier.verify_case(row,directory)

if __name__=='__main__':unittest.main()
