#!/usr/bin/env python3
"""Validate paired measurements and exact responsiveness without timing thresholds."""
import csv
import json
import math
import statistics
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'results'/'tpds'

def require(ok, message):
    if not ok: raise ValueError(message)

def rows(name):
    with (D/name).open(newline='') as f:return list(csv.DictReader(f))

def close(a,b):return math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-12)

def main():
    raw=rows('materializer_raw.csv');cases=rows('materializer_cases.csv');summ=rows('materializer_summary.csv')
    require(len(raw)==600 and len(cases)==60 and len(summ)==12,'incomplete benchmark matrix')
    grouped=defaultdict(dict)
    for r in raw:
        k=(r['family'],r['handles'],r['seed'],r['implementation'])
        require(float(r['seconds'])>0 and r['view_equal']=='True','invalid measured case')
        rep=int(r['repetition']);require(rep not in grouped[k],'duplicate repetition')
        grouped[k][rep]=float(r['seconds'])
    families={'sparse_cut','dense_cut','low_conflict'}
    expected={(f,str(n),str(seed)) for f in families for n in (64,128,256,512) for seed in range(1,6)}
    require({(r['family'],r['handles'],r['seed']) for r in cases}==expected,'case identities differ')
    for c in cases:
        k=(c['family'],c['handles'],c['seed'])
        for method in ('reference','indexed'):
            values=grouped[k+(method,)]
            require(set(values)==set(range(5)),'missing repetitions')
            require(close(c[method+'_seconds'],statistics.median(values.values())),'case median mismatch')
        require(close(c['reference_over_indexed'],float(c['reference_seconds'])/float(c['indexed_seconds'])),'ratio mismatch')
        require(c['view_equal']=='True' and int(c['cells'])<=80000,'invalid evidence state')
    for r in summ:
        selected=[c for c in cases if (c['family'],c['handles'])==(r['family'],r['handles'])]
        ratios=[float(c['reference_over_indexed']) for c in selected]
        require(close(r['paired_speedup_median'],statistics.median(ratios)),'summary median mismatch')
        require(close(r['paired_speedup_min'],min(ratios)) and close(r['paired_speedup_max'],max(ratios)),'summary range mismatch')
    reps=rows('materializer_replications.csv')
    require(len(reps)==9,'replication summary incomplete')
    require({r['execution'] for r in reps}=={'retained-primary','retained-clean','final-current'},'replication labels differ')
    require({r['family'] for r in reps}==families and {r['handles'] for r in reps}=={'512'},'replication matrix differs')
    retained=json.loads((ROOT/'results'/'reproduction.json').read_text())['timing_replication']
    expected_reps=[]
    for label,key in [('retained-primary','primary_summary'),('retained-clean','clean_summary')]:
        expected_reps.extend((label,r) for r in retained[key] if r['handles']=='512')
    expected_reps.extend(('final-current',r) for r in summ if r['handles']=='512')
    lookup={(r['execution'],r['family']):r for r in reps}
    for label,r in expected_reps:
        got=lookup[(label,r['family'])]
        for field in ('reference_median_ms','indexed_median_ms','paired_speedup_median','paired_speedup_min','paired_speedup_max'):
            require(close(got[field],r[field]),'replication value mismatch')
    topo=rows('topology_cases.csv');t=json.loads((D/'topology_summary.json').read_text())
    require(len(topo)==2550 and len({r['blocks'] for r in topo})==51,'topology matrix incomplete')
    keys=set()
    for r in topo:
        blocks=[set(map(int,b.split(','))) for b in r['blocks'].split('|')]
        c=int(r['central']);q=set(map(int,r['quorum'].split(',')))
        k=(r['blocks'],c,tuple(sorted(q)));require(k not in keys,'duplicate placement');keys.add(k)
        require(sorted(v for b in blocks for v in b)==list(range(5)) and len(q)==3,'bad topology')
        cc=sum(len(b) for b in blocks if c in b)
        qq=sum(len(b) for b in blocks if len(b&q)>=2)
        require(int(r['central_responding_sites'])==cc and int(r['quorum_responding_sites'])==qq,'reachability mismatch')
    for role in ('central','quorum'):
        mean=sum(Fraction(int(r[role+'_responding_sites']),5) for r in topo)/len(topo)
        require(str(mean)==t[role+'_mean'],'topology mean mismatch')
    print('PASS: 60 cases / 300 paired repetitions; three 512-handle timing executions retained; 2550 topology placements checked')

if __name__=='__main__':main()
