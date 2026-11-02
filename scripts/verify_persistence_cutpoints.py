"""Passive raw process-cut verifier; imports no producer/service/harness code."""
from pathlib import Path
import argparse,hashlib,json

ROOT=Path(__file__).resolve().parents[1]
RECORDED_SOURCES={
    'cie/__init__.py':'0e091ddb36fa245119cef0482b4506f50e4119807374399c42b0894308799687',
    'cie/model.py':'3464a52306357db15bbd259b76a345a3d06e911485dcd552f2bc60b062ba8668',
    'cie/service.py':'ce70b519bcd8c8ff187f1fffb65332ebe950bd5a206f66bb9f9aa5de9f22c223',
}

def typed_equal(a,b):
    if type(a) is not type(b):return False
    if type(a) is dict:return a.keys()==b.keys() and all(typed_equal(a[k],b[k]) for k in a)
    if type(a) is list:return len(a)==len(b) and all(typed_equal(x,y) for x,y in zip(a,b))
    return a==b

def verify_source_bindings(bindings):
    require(typed_equal(bindings,RECORDED_SOURCES),'recorded source inventory differs')
    changed=[]
    for relative,expected in RECORDED_SOURCES.items():
        if digest((ROOT/'src'/relative).read_bytes())==expected:continue
        captured=ROOT/'results/process-cutpoints-source-preimage'/relative
        require(captured.is_file() and digest(captured.read_bytes())==expected,'exact measured source preimage missing or differs')
        changed.append('src/'+relative)
    return changed

def exact_ack(ack,state,request,result):
    require(type(ack) is dict and set(ack)=={'kind','request','result','state','commits','fsyncs'},'complete ACK fields required')
    expected=dict(kind='ACK',request=request,result=result,state=state,commits=1,fsyncs=2)
    require(typed_equal(ack,expected),'ACK state/request/result/barrier disagreement')

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
    require(type(n) is int and n in (32,32768),'unknown owned input')
    if initial=='absent':before=original_state(n,[])
    elif initial=='accepted0':before=original_state(n,[0])
    elif initial=='accepted01':before=original_state(n,[0,1])
    elif initial=='accepted0_open1':before=original_state(n,[0],partial=True)
    else:raise ValueError('unknown initial state')
    if initial!='absent':
        seed=one_event(record['seed'],'ACK')
        require(type(record['seed']['returncode']) is int and record['seed']['returncode']==0,'baseline process failed')
        exact_ack(seed,before,dict(op='ingest',cells=before['cells']),dict(cells=len(before['cells'])))
    attempt=record['attempt']
    require(attempt['run_ok'] is True,'original process outcome unsuccessful')
    require(type(attempt['returncode']) is int and type(attempt['supervisor_sent_SIGKILL']) is bool,'process outcome types')
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
    require(type(record['recovery']['returncode']) is int and record['recovery']['returncode']==0 and typed_equal(recovered['state'],after),'recovered exact state differs')
    require(typed_equal(recovered['after_state'],after) and recovered['pending_exists'] is False,'recovery mutated state or failed temporary cleanup')
    require(all(cell in after['cells'] for cell in before['cells']),'previously accepted evidence disappeared')
    for ack in acks:
        if operation=='ingest':
            exact_ack(ack,after,dict(op='ingest',cells=original_state(n,[1])['cells']),dict(cells=len(after['cells'])))
        else:
            exact_ack(ack,after,dict(op='ack',floors=[['a','b',1]]),
                dict(member='n0',floors=[['a','b',1]],vectors=original_state(n,[1])['cells']))
    epoch1=[c for c in after['cells'] if c['epoch']==1]
    complete={c['source'] for c in epoch1}=={'v0','v1'}
    require(recovered['floor']['accepted'] is complete,'incomplete/absent floor acknowledged or complete floor refused')
    if complete:
        wanted=dict(accepted=True,result=dict(member='n0',floors=[['a','b',1]],vectors=epoch1))
        require(typed_equal(recovered['floor'],wanted) and typed_equal([recovered['commits'],recovered['fsyncs']],[1,2]),'loaded floor ack missing exact vector/rebarrier')
    else:
        require(set(recovered['floor'])=={'accepted','error'} and type(recovered['floor']['error']) is str,'complete floor refusal required')
        require(typed_equal([recovered['commits'],recovered['fsyncs']],[0,0]),'refused floor unexpectedly committed')
    for kind in ('snapshot','pending'):
        path=directory/(kind+'.bin')
        if kind+'_sha256' in record:
            raw=path.read_bytes()
            require(digest(raw)==record[kind+'_sha256'] and len(raw)==record[kind+'_bytes'],'raw '+kind+' binding failed')
        else:require(not path.exists(),'unrecorded raw persistence file')
    if replacement_finished:require(typed_equal(json.loads((directory/'snapshot.bin').read_bytes()),after),'post-replace visible original bytes differ')
    elif initial!='absent':require(typed_equal(json.loads((directory/'snapshot.bin').read_bytes()),before),'pre-replace old snapshot corrupted')
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
    changed=verify_source_bindings(env['source_files'])
    directories=sorted(root.glob('case-*'));require(len(directories)==protocol['matrix']['total_prespecified_cases']==59,'incomplete prespecified matrix')
    totals=dict(successful_operation_acknowledgements=0,supervised_kills=0,native_partial_temporary_observations=0,floor_ack_accepted_after_reload=0)
    identities=[]
    for i,directory in enumerate(directories):
        row=json.loads((directory/'record.json').read_text());require(type(row['index']) is int and row['index']==i,'case ordering/identity changed')
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
                measured_source_bindings_verified=True,measured_sources_differ_from_current=changed,
                current_source_campaign_claimed=False,
                scope='one-host process termination and exact API-return recovery; not power loss, device durability, WAN or independent machines')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps(verify(a.out),sort_keys=True))
