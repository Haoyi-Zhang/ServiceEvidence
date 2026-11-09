"""Regression checks of retained-data plot consumers, without scientific reruns."""
from pathlib import Path
import csv,hashlib,shutil,subprocess,sys,tempfile,unittest

HERE=Path(__file__).resolve()
if HERE.parents[1].name=='paper':
    PAPER=HERE.parents[1]
    ARTIFACT=PAPER.parent/'artifact'
else:
    ARTIFACT=HERE.parents[3]
    PAPER=ARTIFACT.parent/'paper'
INPUTS=('correctness.csv','compaction.csv','unsealed_safety.csv','tpds/materializer_summary.csv')
RENDER=("from pathlib import Path; import publication_figures as f; "
        "f.paper_style('tpds'); out=Path('rendered'); "
        "f.speed(out,None); f.sparsity(out,None); f.sealing(out,None); f.compaction(out,None)")

class NativePlotInputTests(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        (root/'artifact/figures').mkdir(parents=True)
        (root/'artifact/results/tpds').mkdir(parents=True)
        for name in ('publication_figures.py','figure_style.py'):
            shutil.copy2(ARTIFACT/'figures'/name,root/'artifact/figures'/name)
        for name in INPUTS:shutil.copy2(ARTIFACT/'results'/name,root/'artifact/results'/name)
        return root
    def render(self,root):
        r=subprocess.run([sys.executable,'-B','-c',RENDER],
                         cwd=root/'artifact/figures',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        self.assertEqual(r.returncode,0,r.stdout.decode('utf-8',errors='replace'))
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (root/'artifact/figures/rendered').glob('*.pdf')}
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
            ('compaction.csv','cells_after',lambda old,row:int(old)+37,'compaction-native.pdf'),
            ('tpds/materializer_summary.csv','paired_speedup_median',
             lambda old,row:float(old)+.05,'index-speedup-native.pdf'),
            ('unsealed_safety.csv','sealed_transient_false_merges',
             lambda old,row:max(1,int(row['trials'])//200),'sealing-native.pdf')):
            with self.subTest(input=name):
                root=self.fixture();before=self.render(root)
                self.mutate(root,name,field,value);after=self.render(root)
                self.assertEqual(set(before),set(after))
                self.assertEqual({n for n in before if before[n]!=after[n]},{expected})
        for name,data in protected.items():self.assertEqual((ARTIFACT/'results'/name).read_bytes(),data)
    def test_default_build_redraws_before_latex(self):
        if not (PAPER/'compile.sh').is_file():
            self.skipTest('The LaTeX build order belongs to the complete paper/artifact packet.')
        source=(PAPER/'compile.sh').read_text(encoding='utf-8')
        producer=source.index('figures/publication_figures.py')
        self.assertLess(source.index('check_paper_assets.py'),producer)
        self.assertLess(producer,source.index('pdflatex'))
if __name__=='__main__':unittest.main()
