"""Passive raw process-cut verifier; imports no producer/service/harness code."""
from pathlib import Path
import argparse,hashlib,json

def require(ok,message):
    if not ok:raise ValueError(message)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def original_state(reason,epochs,partial=False):
    cells=[]
    for epoch in epochs:
        for source,vote in [('v0','same'),('v1','unknown')]:
            cells.append(dict(left='a',right='b',epoch=epoch,source=source,vote=vote,reason='R'*reason))
    if partial:cells.append(dict(left='a',right='b',epoch=1,source='v0',vote='same',reason='R'*reason))
    return dict(node_id='n0',sources=['v0','v1'],threshold=1,handles=['a','b'] if cells else [],stable_floors=[],cells=cells)
def one_event(run,kind):
    events=[e for e in run['events'] if e['kind']==kind]
    require(len(events)==1,'exactly one '+kind+' record required')
    return events[0]

def verify_case(record,directory):
    require(record['passed'] is True,'original failed/refused case cannot become an accepted row')
    operation,n,initial,cut=(record[k] for k in ['operation','reason_bytes','initial','cut'])
    require(n in (32,32768),'unknown owned input')
    if initial=='absent':before=original_state(n,[])
    elif initial=='accepted0':before=original_state(n,[0])
    elif initial=='accepted01':before=original_state(n,[0,1])
    elif initial=='accepted0_open1':before=original_state(n,[0],partial=True)
    else:raise ValueError('unknown initial state')
    if initial!='absent':
        seed=one_event(record['seed'],'ACK')
        require(record['seed']['returncode']==0 and seed['state']==before,'baseline was not actually accepted exactly')
        require((seed['commits'],seed['fsyncs'])==(1,2),'baseline barrier incomplete')
    attempt=record['attempt']
    require(attempt['run_ok'],'original process outcome unsuccessful')
    acks=[e for e in attempt['events'] if e['kind']=='ACK']
    if cut!='none':
        point=one_event(attempt,'CUT')
        require(point['name']==cut and attempt['returncode']==-9 and attempt['supervisor_sent_SIGKILL'],'not an actual supervised SIGKILL')
        require(len(acks)==int(cut=='after_dispatch_ack'),'a pre-return cut cannot have a successful acknowledgement')
    else:
        require(attempt['returncode']==0 and not attempt['supervisor_sent_SIGKILL'] and not acks,'refusal control must not succeed')
        one_event(attempt,'REFUSAL')
    replacement_finished=any(e.get('name')=='after_replace' for e in attempt['events'] if e['kind']=='BOUNDARY')
    after=original_state(n,[1] if initial=='absent' else [0,1]) if operation=='ingest' and replacement_finished else before
    recovered=one_event(record['recovery'],'RECOVER')
    require(record['recovery']['returncode']==0 and recovered['state']==after,'recovered exact state differs')
    require(recovered['after_state']==after and recovered['pending_exists'] is False,'recovery mutated state or failed temporary cleanup')
    require(all(cell in after['cells'] for cell in before['cells']),'previously accepted evidence disappeared')
    for ack in acks:
        require(ack['state']==after and (ack['commits'],ack['fsyncs'])==(1,2),'successful return lacks complete persisted state/barriers')
        if operation=='ack':require(ack['result']['vectors']==original_state(n,[1])['cells'],'false acknowledged vector')
    epoch1=[c for c in after['cells'] if c['epoch']==1]
    complete={c['source'] for c in epoch1}=={'v0','v1'}
    require(recovered['floor']['accepted']==complete,'incomplete/absent floor acknowledged or complete floor refused')
    if complete:
        require(recovered['floor']['result']['vectors']==epoch1 and (recovered['commits'],recovered['fsyncs'])==(1,2),'loaded floor ack missing exact vector/rebarrier')
    else:require((recovered['commits'],recovered['fsyncs'])==(0,0),'refused floor unexpectedly committed')
    for kind in ('snapshot','pending'):
        path=directory/(kind+'.bin')
        if kind+'_sha256' in record:
            raw=path.read_bytes()
            require(digest(raw)==record[kind+'_sha256'] and len(raw)==record[kind+'_bytes'],'raw '+kind+' binding failed')
        else:require(not path.exists(),'unrecorded raw persistence file')
    if replacement_finished:require(json.loads((directory/'snapshot.bin').read_bytes())==after,'post-replace visible original bytes differ')
    elif initial!='absent':require(json.loads((directory/'snapshot.bin').read_bytes())==before,'pre-replace old snapshot corrupted')
    if cut=='mid_write_prefix_flushed':
        raw=(directory/'pending.bin').read_bytes()
        target=original_state(n,[1] if initial=='absent' else [0,1]) if operation=='ingest' else before
        whole=json.dumps(target,sort_keys=True,separators=(',',':')).encode()
        require(0<len(raw)<len(whole) and whole.startswith(raw),'cut does not show a true partial temporary write')
        try:json.loads(raw)
        except json.JSONDecodeError:pass
        else:raise ValueError('mid-write temporary unexpectedly complete')
    return dict(successful_operation_acknowledgements=len(acks),supervised_kills=int(cut!='none'),
                native_partial_temporary_observations=int(cut=='mid_write_prefix_flushed'),floor_ack_accepted_after_reload=int(complete))

def verify(root):
    summary=json.loads((root/'summary.json').read_text());protocol=json.loads((root/'protocol.json').read_text());env=json.loads((root/'environment.json').read_text())
    require(env['filesystem'].split()[0]=='ext4','non-ext4 execution')
    require(env['protocol_sha256']==digest((root/'protocol.json').read_bytes()),'protocol identity changed')
    directories=sorted(root.glob('case-*'));require(len(directories)==protocol['matrix']['total_prespecified_cases']==59,'incomplete prespecified matrix')
    totals=dict(successful_operation_acknowledgements=0,supervised_kills=0,native_partial_temporary_observations=0,floor_ack_accepted_after_reload=0)
    identities=[]
    for i,directory in enumerate(directories):
        row=json.loads((directory/'record.json').read_text());require(row['index']==i,'case ordering/identity changed')
        identities.append((row['operation'],row['reason_bytes'],row['initial'],row['cut']))
        result=verify_case(row,directory)
        for key,value in result.items():totals[key]+=value
    require(len(set(identities))==59,'duplicate case disguises missing support')
    cuts=protocol['matrix']['cutpoints']
    expected={('ingest',n,initial,cut) for n in (32,32768) for initial in ('absent','accepted0') for cut in cuts}
    expected|={('ack',n,'accepted01',cut) for n in (32,32768) for cut in cuts}
    expected|={(op,32,'accepted0','none') for op in ('unregistered_source','nonstring_vote','source_equivocation','absent_floor_vector')}
    expected.add(('unsealed_floor_vector',32,'accepted0_open1','none'))
    require(set(identities)==expected,'actual matrix differs from predeclared inputs/cutpoints')
    require(summary['cases']==summary['passed']==59 and summary['failed']==0,'summary contradicts raw rows')
    require(summary['power_loss_test'] is False and summary['independent_machine_test'] is False,'scope improperly widened')
    audit=summary['resource_audit_only']
    require(audit['wall_seconds']<180 and audit['aggregate_CPU_seconds']<90,'predeclared cumulative budget exceeded')
    require(audit['parent_peak_RSS_KiB']+audit['max_child_peak_RSS_KiB']<1024*1024,'memory bound not supported')
    return dict(cases=59,all_raw_state_and_ack_bindings_verified=True,**totals,
                scope='one-host process termination and exact API-return recovery; not power loss, device durability, WAN or independent machines')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps(verify(a.out),sort_keys=True))
