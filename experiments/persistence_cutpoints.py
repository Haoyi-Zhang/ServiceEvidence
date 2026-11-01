"""Owned SIGKILL persistence cutpoints, NOT power-loss/device certification.

Only the supervisor writes results. Child runs the exact owned current Service.
No sockets, external target, old campaign rerun or performance comparison.
"""
from __future__ import annotations
import argparse,asyncio,base64,hashlib,json,os,platform,resource,selectors,signal,stat,subprocess,sys,tempfile,time
from pathlib import Path

CUTS=('before_write','mid_write_prefix_flushed','before_file_fsync','after_file_fsync','before_replace','after_replace','before_directory_fsync','after_directory_fsync','after_dispatch_ack')
HERE=Path(__file__).resolve()
def need(ok,msg):
    if not ok:raise RuntimeError(msg)
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def sha(data):return hashlib.sha256(data).hexdigest()
def emit(kind,**data):print(json.dumps(dict(kind=kind,**data),sort_keys=True),flush=True)
def fixture(n,epochs):
    cells=[dict(left='a',right='b',epoch=e,source=s,vote='same' if s=='v0' else 'unknown',reason='R'*n) for e in epochs for s in ('v0','v1')]
    return dict(node_id='n0',sources=['v0','v1'],threshold=1,handles=['a','b'] if cells else [],stable_floors=[],cells=cells)
def ingestion(n):return dict(op='ingest',cells=fixture(n,[1])['cells'])

def child(args):
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(5,5))
    sys.path.insert(0,str(args.src))
    import cie.service as api
    stats=api.WireStats()
    service=api.Service('n0',['v0','v1'],1,[],['n0'],args.snapshot,stats=stats)
    def point(name):
        emit('BOUNDARY',name=name)
        if args.cut==name:
            emit('CUT',name=name)
            # Supervisor kills this exact child. No cleanup handler is run.
            while True:signal.pause()
    if args.mode=='operate':
        original_open=Path.open;original_fsync=api.os.fsync;original_replace=api.os.replace;original_directory=api.fsync_directory
        class Stream:
            def __init__(self,stream):self.stream=stream
            def __enter__(self):self.stream.__enter__();return self
            def __exit__(self,*a):return self.stream.__exit__(*a)
            def __getattr__(self,name):return getattr(self.stream,name)
            def write(self,text):
                point('before_write')
                if args.cut=='mid_write_prefix_flushed':
                    split=max(1,len(text)//2);count=self.stream.write(text[:split]);self.stream.flush()
                    point('mid_write_prefix_flushed')
                    return count+self.stream.write(text[split:])
                return self.stream.write(text)
        def opened(path,*a,**kw):
            stream=original_open(path,*a,**kw)
            return Stream(stream) if path==args.snapshot.with_suffix('.pending') and a and a[0]=='w' else stream
        def synced(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode):
                point('before_file_fsync');result=original_fsync(fd);point('after_file_fsync');return result
            return original_fsync(fd)
        def replaced(source,dest):
            point('before_replace');result=original_replace(source,dest);point('after_replace');return result
        def directory(path):
            point('before_directory_fsync');result=original_directory(path);point('after_directory_fsync');return result
        Path.open=opened;api.os.fsync=synced;api.os.replace=replaced;api.fsync_directory=directory
    if args.mode=='seed':
        request=dict(op='ingest',cells=fixture(args.reason,range(args.epochs))['cells'])
        if args.operation=='partial_seed':request['cells']+=fixture(args.reason,[1])['cells'][:1]
    elif args.mode=='operate':request=ingestion(args.reason) if args.operation=='ingest' else dict(op='ack',floors=[['a','b',1]])
    elif args.mode=='recover':
        state=service.replica.export_state()
        try:
            ack=asyncio.run(service.dispatch(dict(op='ack',floors=[['a','b',1]])))
            floor=dict(accepted=True,result=ack)
        except ValueError as exc:floor=dict(accepted=False,error=str(exc))
        emit('RECOVER',state=state,after_state=service.replica.export_state(),floor=floor,commits=stats.commits,fsyncs=stats.fsyncs,pending_exists=args.snapshot.with_suffix('.pending').exists())
        return
    else:
        request=ingestion(args.reason)
        if args.operation=='unregistered_source':request['cells'][0]['source']='foreign'
        elif args.operation=='nonstring_vote':request['cells'][0]['vote']=True
        elif args.operation=='source_equivocation':request['cells'][0].update(epoch=0,vote='different')
        elif args.operation=='absent_floor_vector':request=dict(op='ack',floors=[['a','b',9]])
        elif args.operation=='unsealed_floor_vector':request=dict(op='ack',floors=[['a','b',1]])
    try:
        result=asyncio.run(service.dispatch(request))
        emit('ACK',request=request,result=result,state=service.replica.export_state(),commits=stats.commits,fsyncs=stats.fsyncs)
        if args.mode=='operate':point('after_dispatch_ack')
    except (ValueError,OSError) as exc:emit('REFUSAL',error=type(exc).__name__+': '+str(exc),state=service.replica.export_state())

def supervise(args):
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    need(os.name=='posix','POSIX native process kill required')
    out=args.out.resolve();need(not out.exists(),'Fresh result directory required; no overwrite/retry')
    protocol=json.loads(args.protocol.read_text());need(protocol['matrix']['total_prespecified_cases']==59,'Wrong predeclared protocol')
    out.mkdir(parents=True)
    (out/'protocol.json').write_bytes(args.protocol.read_bytes())
    start=time.monotonic();cpu0=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime
    rows=[];byte_total=0
    def budget():
        own=resource.getrusage(resource.RUSAGE_SELF);children=resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu=own.ru_utime+own.ru_stime+children.ru_utime+children.ru_stime-cpu0
        need(time.monotonic()-start<180 and cpu<90,'Cumulative campaign budget exhausted; no reset')
        return cpu
    def run(mode,path,n,*,operation='ingest',cut='none',epochs=1):
        budget()
        command=[sys.executable,'-I','-B',str(HERE),'--child','--mode',mode,'--snapshot',str(path),'--src',str(args.src.resolve()),'--reason',str(n),'--operation',operation,'--cut',cut,'--epochs',str(epochs)]
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        events=[];deadline=min(start+180,time.monotonic()+5);killed=False;buffer=b'';failure=None;error=b''
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
        try:
            while True:
                need(time.monotonic()<deadline,'child wall deadline exceeded')
                ready=selector.select(max(0,min(.1,deadline-time.monotonic())))
                if not ready:
                    if process.poll() is not None:break
                    continue
                chunk=os.read(process.stdout.fileno(),262144)
                if not chunk:break
                buffer+=chunk;need(len(buffer)<=1_000_000,'event buffer cap')
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1);event=json.loads(line);events.append(event)
                    if event['kind']=='CUT':
                        need(event['name']==cut,'wrong cut reached');process.kill();killed=True;break
                if killed:break
            _,error=process.communicate(timeout=max(.1,deadline-time.monotonic()))
        except Exception as exc:failure=type(exc).__name__+': '+str(exc)
        finally:
            selector.close()
            if process.poll() is None:process.kill();process.wait()
        success=killed and process.returncode==-signal.SIGKILL if cut!='none' else process.returncode==0
        return dict(mode=mode,operation=operation,cut=cut,events=events,returncode=process.returncode,supervisor_sent_SIGKILL=killed,stderr=error.decode('utf-8','replace'),run_ok=success and failure is None,failure=failure)
    with tempfile.TemporaryDirectory(prefix='service-evidence-owned-processcuts-') as temporary:
        root=Path(temporary);mount=subprocess.run(['findmnt','-T',str(root),'-no','FSTYPE,OPTIONS'],capture_output=True,text=True,check=True).stdout.strip()
        need(mount.split()[0]=='ext4','Refuse non-ext4 scratch; do not substitute drvfs/tmpfs')
        environment=dict(platform=platform.platform(),python=sys.version,filesystem=mount,device_id=root.stat().st_dev,ext4_runtime_temporary=str(root),source_files={str(p.relative_to(args.src)):sha(p.read_bytes()) for p in sorted(args.src.rglob('*.py'))},protocol_sha256=sha(args.protocol.read_bytes()),scope='one WSL host; no power loss or device guarantee')
        (out/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
        matrix=[('ingest',n,initial,cut) for n in (32,32768) for initial in ('absent','accepted0') for cut in CUTS]
        matrix += [('ack',n,'accepted01',cut) for n in (32,32768) for cut in CUTS]
        matrix += [(op,32,'accepted0','none') for op in ('unregistered_source','nonstring_vote','source_equivocation','absent_floor_vector')]
        matrix += [('unsealed_floor_vector',32,'accepted0_open1','none')]
        for index,(operation,n,initial,cut) in enumerate(matrix):
            case=dict(index=index,operation=operation,reason_bytes=n,initial=initial,cut=cut,passed=False)
            case_dir=out/f'case-{index:03d}';case_dir.mkdir();scratch=root/f'case-{index:03d}';scratch.mkdir();snapshot=scratch/'state.json'
            try:
                baseline=fixture(n,[] if initial=='absent' else [0] if initial=='accepted0' else [0,1])
                if initial=='accepted0_open1':baseline=fixture(n,[0]);baseline['cells']+=fixture(n,[1])['cells'][:1]
                if initial!='absent':
                    seed=run('seed',snapshot,n,epochs=1 if initial in ('accepted0','accepted0_open1') else 2,operation='partial_seed' if initial=='accepted0_open1' else 'ingest');case['seed']=seed
                    need(seed['run_ok'],'seed process failed')
                    need(len([e for e in seed['events'] if e['kind']=='ACK'])==1,'baseline not actually acknowledged')
                    need(seed['events'][-1]['state']==baseline,'baseline exact-state mismatch')
                attempt=run('operate' if cut!='none' else 'negative',snapshot,n,operation=operation,cut=cut);case['attempt']=attempt
                need(attempt['run_ok'],'actual process cut/operation failed: '+str(attempt.get('failure')))
                # Preserve actual pre-recovery file bytes, including partial temp.
                for name,path in [('snapshot',snapshot),('pending',snapshot.with_suffix('.pending'))]:
                    if path.exists():
                        raw=path.read_bytes();need(len(raw)<=1048576,'snapshot cap');byte_total+=len(raw)
                        (case_dir/(name+'.bin')).write_bytes(raw);case[name+'_sha256']=sha(raw);case[name+'_bytes']=len(raw)
                need(byte_total<=100*1024**2,'retained application byte cap')
                recovery=run('recover',snapshot,n);case['recovery']=recovery
                need(recovery['run_ok'],'recovery process failed')
                recovered=next(e for e in recovery['events'] if e['kind']=='RECOVER');state=recovered['state']
                new=fixture(n,[1] if initial=='absent' else [0,1])
                if operation=='ingest':
                    expected=baseline if cut in CUTS[:5] else new
                    need(state==expected,'cut did not recover exact expected old/new state')
                else:need(state==baseline,'ack/refusal altered exact state')
                need(all(cell in state['cells'] for cell in baseline['cells']),'previously acknowledged evidence lost')
                acks=[e for e in attempt['events'] if e['kind']=='ACK']
                need(len(acks)==(1 if cut=='after_dispatch_ack' else 0),'ack incorrectly reported before successful dispatch return')
                if acks:
                    need(acks[0]['state']==state,'successful API acknowledgement did not survive process kill')
                    if operation=='ack':need(acks[0]['fsyncs']==2 and acks[0]['commits']==1,'reloaded floor ack omitted persistence barrier')
                complete_epoch1=state==fixture(n,[0,1]) or state==fixture(n,[1])
                need(recovered['floor']['accepted']==complete_epoch1,'missing/sealed floor acknowledgement mismatch')
                if complete_epoch1:
                    need(recovered['floor']['result']['vectors']==fixture(n,[1])['cells'],'false floor-vector acknowledgement')
                    need((recovered['commits'],recovered['fsyncs'])==(1,2),'recovery ack barrier missing')
                need(recovered['after_state']==state and not recovered['pending_exists'],'recovery changed state or left stale temp')
                if cut=='mid_write_prefix_flushed':need(0<case.get('pending_bytes',0)<len(encoded(new if operation=='ingest' else baseline)),'real partial temporary write not observed')
                if cut=='none':need(any(e['kind']=='REFUSAL' for e in attempt['events']),'negative request did not refuse')
                case['passed']=True
            except Exception as exc:case['failure']=type(exc).__name__+': '+str(exc)
            record=encoded(case)+b'\n';byte_total+=len(record);need(byte_total<=100*1024**2,'retained application record cap')
            (case_dir/'record.json').write_bytes(record)
            rows.append({k:v for k,v in case.items() if k not in ('seed','attempt','recovery')})
            budget()
    usage=resource.getrusage(resource.RUSAGE_SELF);children=resource.getrusage(resource.RUSAGE_CHILDREN)
    summary=dict(cases=len(rows),passed=sum(r['passed'] for r in rows),failed=sum(not r['passed'] for r in rows),actual_SIGKILL_cases=sum(r['cut']!='none' for r in rows),negative_controls=5,rows=rows,
                 resource_audit_only=dict(wall_seconds=time.monotonic()-start,aggregate_CPU_seconds=budget(),parent_peak_RSS_KiB=usage.ru_maxrss,max_child_peak_RSS_KiB=children.ru_maxrss),retained_snapshot_bytes=byte_total,
                 scientific_latency_or_throughput_claim=False,power_loss_test=False,independent_machine_test=False,production_code_modified=False)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))
    return 0 if not summary['failed'] else 1

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--child',action='store_true');p.add_argument('--src',type=Path,required=True)
    p.add_argument('--snapshot',type=Path);p.add_argument('--mode',choices=['seed','operate','recover','negative']);p.add_argument('--reason',type=int,default=32);p.add_argument('--epochs',type=int,default=1)
    p.add_argument('--operation',default='ingest');p.add_argument('--cut',default='none');p.add_argument('--protocol',type=Path);p.add_argument('--out',type=Path)
    args=p.parse_args();return child(args) if args.child else supervise(args)
if __name__=='__main__':raise SystemExit(main())
