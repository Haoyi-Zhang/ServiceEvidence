"""Regression checks of retained-data plot consumers, without scientific reruns."""
from pathlib import Path
import csv,hashlib,shutil,subprocess,sys,tempfile,unittest

PAPER=Path(__file__).resolve().parents[1]
ARTIFACT=PAPER.parent/'artifact'
INPUTS=('correctness.csv','compaction.csv','unsealed_safety.csv')

class NativePlotInputTests(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        (root/'paper/figures').mkdir(parents=True)
        (root/'paper/tables').mkdir()
        (root/'artifact/results').mkdir(parents=True)
        shutil.copy2(PAPER/'figures/draw_native.py',root/'paper/figures/draw_native.py')
        shutil.copy2(PAPER/'tables/index-speedup.csv',root/'paper/tables/index-speedup.csv')
        for name in INPUTS:shutil.copy2(ARTIFACT/'results'/name,root/'artifact/results'/name)
        return root
    def render(self,root):
        r=subprocess.run([sys.executable,'-B',str(root/'paper/figures/draw_native.py')],
                         cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        self.assertEqual(r.returncode,0,r.stdout.decode('utf-8',errors='replace'))
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (root/'paper/figures').glob('*.pdf')}
    def mutate(self,root,name,field,value):
        path=root/'artifact/results'/name
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
        if name=='correctness.csv':
            row=next(r for r in rows if r['method']=='sealed-evidence q=2')
        else:row=rows[0]
        row[field]=str(value(row[field],row))
        with path.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    def test_each_retained_input_reaches_its_own_numerical_plot(self):
        protected={name:(ARTIFACT/'results'/name).read_bytes() for name in INPUTS}
        for name,field,value,expected in (
            ('correctness.csv','false_split_rate',lambda old,row:float(old)+.01,'sparsity-native.pdf'),
            ('compaction.csv','cells_after',lambda old,row:int(old)+1,'compaction-native.pdf'),
            ('unsealed_safety.csv','sealed_transient_false_merges',
             lambda old,row:max(1,int(row['trials'])//200),'sealing-native.pdf')):
            with self.subTest(input=name):
                root=self.fixture();before=self.render(root)
                self.mutate(root,name,field,value);after=self.render(root)
                self.assertEqual(set(before),set(after))
                self.assertEqual({n for n in before if before[n]!=after[n]},{expected})
        for name,data in protected.items():self.assertEqual((ARTIFACT/'results'/name).read_bytes(),data)
    def test_default_build_redraws_before_latex(self):
        source=(PAPER/'compile.sh').read_text(encoding='utf-8')
        self.assertLess(source.index('check_paper_assets.py'),source.index('python figures/draw_native.py'))
        self.assertLess(source.index('python figures/draw_native.py'),source.index('pdflatex'))
if __name__=='__main__':unittest.main()
