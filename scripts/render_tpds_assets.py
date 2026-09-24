#!/usr/bin/env python3
"""Derive TPDS tables and scalar macros from retained experimental results."""
from pathlib import Path
import argparse, csv, json, statistics
ROOT=Path(__file__).resolve().parents[1]
def rows(name):
    with (ROOT/'results'/name).open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output; out.mkdir(parents=True,exist_ok=True)
    scale=max(rows('scale.csv'),key=lambda r:int(r['observations']))
    eq=json.loads((ROOT/'results/equal_work_summary.json').read_text())['architectures']
    pc=rows('process_crash.csv')
    nums={'ProcessMin':f"{min(float(x['elapsed_seconds']) for x in pc):.2f}",
          'ProcessMax':f"{max(float(x['elapsed_seconds']) for x in pc):.2f}",
          'ScaleRss':f"{float(scale['peak_rss_mib']):.1f}",
          'ScaleTime':f"{float(scale['total_seconds']):.2f}",
          'ScaleCertMedian':f"{float(scale['certificate_ms_median']):.1f}",
          'ScaleCertPtail':f"{float(scale['certificate_ms_p95']):.1f}"}
    for key, name in [('central-recompute','Central'),('coordinated-quorum','Quorum'),('peer-evidence','Peer')]:
        nums['Equal'+name+'Time']=f"{eq[key]['elapsed_seconds_median']:.2f}"
    (out/'measured-values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in nums.items()))
    lines=[r'\begin{table}[t]\centering',r'\caption{Independent certificate checks. Generation and verification are median milliseconds; size is median serialized bytes.}',r'\label{tab:certs}\small',r'\begin{tabular}{lrrrr}\toprule',r'Kind & Count & Bytes & Generate & Verify\\\midrule']
    witness=rows('witnesses.csv')
    for kind in ['same','different','ambiguous']:
        selected=[r for r in witness if r['kind']==kind]
        med=lambda k:statistics.median(float(r[k]) for r in selected)
        lines.append(f"{kind} & {len(selected)} & {med('certificate_bytes'):.0f} & {med('generation_ms'):.2f} & {med('verification_ms'):.2f}"+r'\\')
    lines += [r'\bottomrule\end{tabular}\end{table}']
    (out/'certificates.tex').write_text('\n'.join(lines)+'\n')
    lines=[r'\begin{table}[t]\centering',r'\caption{Equal-work ranges across ten cases per architecture. Response percentages use the two measured cuts; byte columns are MiB.}',r'\label{tab:equal-work-ranges}\scriptsize',r'\begin{tabular}{lrrrr}\toprule',r'Architecture & Response & Wire & Persisted & Time (s)\\\midrule']
    for key,name,avail in [('central-recompute','Central','40/60'),('coordinated-quorum','Quorum','60/60'),('peer-evidence','Peer','100/100')]:
        r=eq[key]; vals=[]
        for field in ['wire_bytes','persistence_bytes_written','elapsed_seconds']:
            v=r[field+'_range']; div=1 if field=='elapsed_seconds' else 1024**2
            vals.append(f"{v['min']/div:.2f}--{v['max']/div:.2f}")
        lines.append(' & '.join([name,avail+r'\%']+vals)+r'\\')
    lines += [r'\bottomrule\end{tabular}\end{table}']
    (out/'equal-ranges.tex').write_text('\n'.join(lines)+'\n')
    bench=rows('tpds/materializer_summary.csv')
    with (out/'index-speedup.csv').open('w',newline='') as f:
        writer=csv.writer(f); writer.writerow(['handles','sparse_cut','dense_cut','low_conflict'])
        for n in [64,128,256,512]:
            writer.writerow([n]+[next(r['paired_speedup_median'] for r in bench if int(r['handles'])==n and r['family']==family) for family in ['sparse_cut','dense_cut','low_conflict']])
    print('Rendered TPDS values, certificates, ranges, and paired timing plot.')
if __name__=='__main__': main()
