"""Verify a fresh same-work durable cohort; read only unless --json-out supplied."""
import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

from cie.model import Replica
from cie.mutex_baseline import priority_preserving_mws
from cie.service import pack,bounded_response

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('durable_raw_checker',ROOT/'checker/verify.py')
checker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

def require(condition,message):
    if not condition: raise ValueError(message)

def verify(out):
    summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
    require(summary.get('durable_service_costs_measured') is True,'not a durable cohort')
    before=json.loads((out/'source-before.json').read_text(encoding='utf-8'))
    after=json.loads((out/'source-after.json').read_text(encoding='utf-8'))
    require(before==after and summary['source_unchanged'] is True,'source changed')
    require(set(before)=={'experiments/workflow_mws.py','experiments/materializer_campaign.py',
        'src/cie/model.py','src/cie/service.py','src/cie/mutex_baseline.py',
        'checker/verify.py','scripts/verify_durable_workflow_mws.py'},'missing implementation identities')
    require(all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value
                for name,value in before.items()),'measured source differs from replay source')
    probe=json.loads((out/'native-persistence-probe.json').read_text(encoding='utf-8'))
    require(probe['acknowledged'] and probe['error'] is None and not probe['substitute_used'],'durability probe failed')
    require(not list(out.glob('FAILED-*.json.gz')),'failed case is not an accepted cohort')
    expected={(f,n,s,a) for f in ('sparse_cut','dense_cut','low_conflict')
        for n in (64,128) for s in (1,2) for a in ('indexed','mws_small_table','scanning')}
    inputs=[(f,n,s) for f in ('sparse_cut','dense_cut','low_conflict')
        for n in (64,128) for s in (1,2)]
    arms=('indexed','mws_small_table','scanning')
    expected_order=[(*key,arm) for i,key in enumerate(inputs)
        for arm in arms[i%3:]+arms[:i%3]]
    require([tuple(r[k] for k in ('family','handles','seed','implementation'))
        for r in summary['cases']]==expected_order,'implementation order is not counterbalanced')
    seen=set(); common={}; rows=[]
    events=checks=requests=wire_bytes=restarts=commits=fsyncs=snapshot_bytes=0
    schedule=Counter(initial_update=3,partition_query=3,initial_repair=6,
        complete_query=3,later_update=3,later_repair=6,later_query=3,
        floor_reports=3,floor_acks=3,compaction=3,floor_repair=6,
        final_query=3,post_restart_query=3)
    for path in sorted(out.glob('*.json.gz')):
        with gzip.open(path,'rt',encoding='utf-8') as stream: data=json.load(stream)
        row=data['row']
        key=tuple(row[k] for k in ('family','handles','seed','implementation'))
        require(key not in seen,'duplicate case'); seen.add(key)
        require(row in summary['cases'],'raw row not in summary')
        if key[:3] in common:
            require(data['input_state']==common[key[:3]],'baseline input information differs')
        common[key[:3]]=data['input_state']
        require(row['all_predicates_pass'] and row['volatile_commits']==0,'volatile/failed arm')
        require(row['durable_commits']==27 and row['fsyncs']==54 and row['snapshot_bytes']>0,'durable mutation accounting')
        require(row['orderly_restarts']==len(data['restarts'])==3,'restart evidence missing')
        phases=Counter(event['phase'] for event in data['events'])
        require(phases==schedule and len(data['events'])==row['top_level_events']==48,'phase schedule mismatch')
        phase_costs={p:sum(e['rpc_ns']+e.get('checker_ns',0) for e in data['events'] if e['phase']==p)
                     for p in phases}
        phase_costs['snapshot_reload']=sum(r['reload_ns'] for r in data['restarts'])
        require(phase_costs==row['phases_including_checker_ns'],'phase timing mismatch')
        for event in data['events']:
            require(event['rpc_ns']>0,'nonpositive RPC time')
            if event['request']['op']=='query':
                answer=event['response']
                checker.verify(answer['state'],answer['certificate'])
                r=Replica.import_state(answer['state'])
                require(r.materialize()==r.materialize_reference()==priority_preserving_mws(r),'whole-view mismatch')
                checks+=1
        for restart in data['restarts']:
            require(restart['reload_ns']>0,'missing measured orderly reload cost')
            require(restart['before']==restart['recovered'],'acknowledged state lost on orderly reload')
            saved=json.loads((out/'snapshots'/restart['snapshot']).read_text(encoding='utf-8'))
            require(saved==restart['recovered'],'retained snapshot disagrees with restart')
            restart_answers=[e['response'] for e in data['events']
                if e['phase']=='post_restart_query' and e['response']['state']['node_id']==restart['node']]
            require(len(restart_answers)==1 and restart_answers[0]['state']==saved,'post-restart query/state mismatch')
            restarts+=1
        require(row['wire_requests']==84 and len(data['peer_frames'])==36,'RPC/nested-frame count')
        frames=data['events']+data['peer_frames']
        size=sum(len(pack(e['request']))+len(bounded_response(e['request'],e['response'])) for e in frames)
        require(size==row['wire_bytes'],'raw frame byte accounting')
        events+=len(data['events']); requests+=row['wire_requests']; wire_bytes+=size
        commits+=row['durable_commits']; fsyncs+=row['fsyncs']; snapshot_bytes+=row['snapshot_bytes']
        rows.append(row)
    require(seen==expected and len(rows)==summary['case_count']==36 and len(common)==12,'incomplete case matrix')
    require((events,checks,requests,wire_bytes)==(summary['raw_event_count'],summary['certificate_checks'],
        summary['total_wire_requests'],summary['total_wire_bytes']),'summary totals mismatch')
    costs=[]
    for family in ('sparse_cut','dense_cut','low_conflict'):
        for arm in ('indexed','mws_small_table','scanning'):
            group=[r for r in rows if r['family']==family and r['handles']==128 and r['implementation']==arm]
            costs.append(dict(family=family,handles=128,implementation=arm,seeds=len(group),
                median_workflow_ms=round(statistics.median(r['workflow_ns']/1e6 for r in group),3)))
    return dict(status='verified_fresh_durable_cohort',cases=36,input_graphs=12,
        query_checks=checks,orderly_restarts=restarts,raw_events=events,requests=requests,
        wire_bytes=wire_bytes,durable_commits=commits,fsyncs=fsyncs,snapshot_bytes=snapshot_bytes,
        source_unchanged=True,mismatches=0,costs_128_handles=costs,
        boundary='same-host loopback with orderly reloads; not power loss, independent-process crash or deployment ranking')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--json-out',type=Path)
    args=p.parse_args()
    result=verify(args.out)
    if args.json_out: args.json_out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,separators=(',',':')))
