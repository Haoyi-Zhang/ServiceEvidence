import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest

from cie.model import EvidenceCell, Vote

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location(name,ROOT/'experiments'/f'{name}.py')
    loaded = importlib.util.module_from_spec(spec)
    sys.path.insert(0,str(ROOT/'experiments'))
    try:
        spec.loader.exec_module(loaded)
    finally:
        sys.path.pop(0)
    return loaded


class RetentionObligationTests(unittest.TestCase):
    def test_equal_mws_view_does_not_imply_equal_retention(self):
        result = module('retention_obligation').witness()
        self.assertEqual(result['retained_cells'],[3,6,3])
        self.assertTrue(result['equal_certificates'])
        self.assertFalse(result['plain_log_satisfies_retention'])

    def test_persistent_arm_binds_mws_on_load_and_post_replace_failure(self):
        workflow = module('workflow_mws')
        # This is a native failed-ack regression, not a successful durability test.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'
            service = workflow.PersistentMaterializedService('n',['s'],1,['a','b'],['n'],path,
                implementation='mws_small_table')
            cell = EvidenceCell('a','b',0,'s',Vote.SAME,'owned binding test')
            proposed = type(service.replica).import_state(service.replica.export_state())
            proposed.add(cell)
            try:
                service._commit(proposed)
            except OSError:
                pass
            self.assertEqual(service.replica.materialize(), workflow.priority_preserving_mws(service.replica))
            loaded = workflow.PersistentMaterializedService('n',['s'],1,['a','b'],['n'],path,
                implementation='mws_small_table')
            self.assertEqual(loaded.replica.materialize(), service.replica.materialize())


if __name__ == '__main__':
    unittest.main()
