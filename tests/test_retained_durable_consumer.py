"""Historical raw tables use measured source, never relabeled current timing."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import render_durable_mws as renderer

class RetainedDurableConsumerTests(unittest.TestCase):
    def test_measured_source_context_regenerates_the_same_values(self):
        result=renderer.retained()
        self.assertEqual(result['status'],'verified_retained_measured_cohort')
        self.assertFalse(result['current_source_campaign_claimed'])
        self.assertIn('src/cie/service.py',result['measured_source_differences'])
        self.assertEqual((result['cases'],result['query_checks']),(36,540))
        self.assertEqual(renderer.table(result),(ROOT.parent/'paper/tables/primary-mws-study.tex').read_text(encoding='utf-8'))

    def test_tampered_measured_preimage_fails_before_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            data=Path(directory)
            name='src/cie/service.py';target=data/'source-preimage'/name
            target.parent.mkdir(parents=True);target.write_text('modified',encoding='utf-8')
            (data/'source-before.json').write_text(json.dumps({name:'0'*64}),encoding='utf-8')
            with patch.object(renderer,'DATA',data),self.assertRaisesRegex(ValueError,'preimage differs'):
                renderer.retained()

if __name__=='__main__':unittest.main()
