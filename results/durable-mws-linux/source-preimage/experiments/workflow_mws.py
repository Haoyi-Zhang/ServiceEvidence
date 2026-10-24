"""Same-contract native loopback comparison; no remote targets.

The default is volatile; --persistence durable requires Linux and uses the
unchanged POSIX file-and-directory-fsync Service in every arm. Every
implementation receives identical source batches, epoch changes and floor
protocol, and every query is checked against its coupled state.
"""
from __future__ import annotations
import argparse
import asyncio
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import time

from cie.model import EvidenceCell, Replica, Vote
from cie.mutex_baseline import priority_preserving_mws
from cie.service import Service, WireStats, rpc, common_floor_reports
from cie import service as service_module
from materializer_campaign import instance

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workflow_checker', ROOT/'checker/verify.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def require(value, message):
    if not value:
        raise ValueError(message)


def clock_record():
    return {name: vars(time.get_clock_info(name)) for name in
            ('time', 'monotonic', 'perf_counter', 'process_time')}


def source_binding():
    """Consumed owned implementation/checker bytes, not historical attribution."""
    names = ('experiments/workflow_mws.py','experiments/materializer_campaign.py',
             'src/cie/model.py','src/cie/service.py','src/cie/mutex_baseline.py',
             'checker/verify.py','scripts/verify_durable_workflow_mws.py')
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}


def environment():
    host = None
    if sys.platform == 'win32':
        command = ("[pscustomobject]@{cpu=Get-CimInstance Win32_Processor | "
                   "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors; "
                   "os=Get-CimInstance Win32_OperatingSystem | "
                   "Select-Object Caption,Version,BuildNumber,OSArchitecture,TotalVisibleMemorySize; "
                   "volume=Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='D:'\" | "
                   "Select-Object FileSystem,DriveType} | ConvertTo-Json -Depth 5")
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                                capture_output=True, timeout=20)
        require(result.returncode == 0, 'host inventory failed')
        host = json.loads(result.stdout.decode('utf-8-sig'))
    return dict(python=sys.version, python_executable=sys.executable,
                platform=platform.platform(), sqlite=sqlite3.sqlite_version,
                sqlite_role='runtime inventory only; this service does not use SQLite',
                clocks=clock_record(), host=host, affinity='not pinned',
                allocation_limit='unknown', virtualization='unknown',
                persistence_medium='unknown',
                scope='this execution only; no historical environment attribution')


class VolatileService(Service):
    """Explicit memory-only experimental owner; not a durability substitution."""
    def __init__(self, *args, implementation, **kwargs):
        self.implementation = implementation
        self.volatile_commits = 0
        super().__init__(*args, **kwargs)

    def _commit(self, proposed):
        self._admit(proposed)
        if self.implementation == 'scanning':
            proposed.materialize = proposed.materialize_reference
        elif self.implementation == 'mws_small_table':
            proposed.materialize = lambda: priority_preserving_mws(proposed)
        self.replica = proposed
        self.volatile_commits += 1


class PersistentMaterializedService(Service):
    """Same snapshot/ack protocol in every arm; only the view kernel differs."""
    def __init__(self, *args, implementation, **kwargs):
        self.implementation = implementation
        self.volatile_commits = 0
        super().__init__(*args, **kwargs)
        self._bind_view()

    def _bind_view(self):
        if self.implementation == 'scanning':
            self.replica.materialize = self.replica.materialize_reference
        elif self.implementation == 'mws_small_table':
            self.replica.materialize = lambda: priority_preserving_mws(self.replica)

    def _commit(self, proposed):
        try:
            super()._commit(proposed)
        finally:
            # Also preserve the arm after an unacknowledged post-replace error.
            self._bind_view()


async def native_persistence_probe(out):
    service = Service('probe', ['s'], 1, ['a','b'], ['probe'], out/'probe'/'state.json')
    error = None
    try:
        await service.dispatch({'op':'ingest', 'cells':[
            EvidenceCell('a','b',0,'s',Vote.SAME,'owned native boundary').to_dict()]})
    except OSError as exc:
        error = dict(type=type(exc).__name__, errno=exc.errno, winerror=getattr(exc,'winerror',None))
    return dict(acknowledged=error is None, error=error,
                replaced_snapshot_exists=service.snapshot.exists(),
                cells_in_memory=len(service.replica),
                contract='unchanged Service: content fsync + replace + parent directory fsync',
                substitute_used=False, power_loss_test=False)


async def case(out, family, n, seed, implementation, persistent=False):
    start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    r = instance(family, n, seed)
    # All names are synthetic handles; no URLs, scanners or acquired payloads.
    members = ['n0','n1','n2']
    wire = WireStats()
    owner_type = PersistentMaterializedService if persistent else VolatileService
    snapshot_dir = 'snapshots' if persistent else 'unused-volatile-paths'
    owners = [owner_type(node, list(r.sources), r.threshold, list(r.handles), members,
              out/snapshot_dir/f'{family}-{n}-{seed}-{implementation}-{node}.json',
              wire, implementation=implementation) for node in members]
    events, peer_frames, restarts = [], [], []
    query = (r.handles[0], r.handles[-1]) if family == 'low_conflict' else (r.handles[0],r.handles[1])
    ports = []
    original_peer_rpc = service_module.rpc

    async def recorded_peer_rpc(port, request, stats=None):
        # Instrumentation delegates to the real loopback RPC. No transport,
        # persistence or decision mechanism is replaced by this recorder.
        answer = await original_peer_rpc(port, request, stats)
        peer_frames.append(dict(port=port,request=request,response=answer))
        return answer
    async def call(node, request, phase):
        t = time.perf_counter_ns()
        answer = await rpc(ports[node], request, wire)
        events.append(dict(phase=phase,node=node,request=request,response=answer,
                           rpc_ns=time.perf_counter_ns()-t))
        if request['op'] == 'query':
            t = time.perf_counter_ns()
            checker.verify(answer['state'], answer['certificate'])
            events[-1]['checker_ns'] = time.perf_counter_ns()-t
        require(time.perf_counter_ns()-start < 120_000_000_000, '120-second case cap')
        return answer

    async def heal(phase):
        for a in range(3):
            for b in range(3):
                if a != b:
                    await call(a, {'op':'pull','peer_port':ports[b]}, phase)

    service_module.rpc = recorded_peer_rpc
    try:
        for owner in owners:
            ports.append(await owner.start())
        for i, source in enumerate(r.sources):
            await call(i, {'op':'ingest','cells':[c.to_dict() for c in r.cells if c.source == source]}, 'initial_update')
        partial = [await call(i, {'op':'query','left':query[0],'right':query[1]}, 'partition_query') for i in range(3)]
        require(all(x['certificate']['kind'] == 'ambiguous' for x in partial), 'partial closure')
        await heal('initial_repair')
        initial = [await call(i, {'op':'query','left':query[0],'right':query[1]}, 'complete_query') for i in range(3)]
        expected = r.certificate(*query)
        require(all(x['certificate'] == expected for x in initial), 'same-semantic complete query')
        # Actual later sealed epoch; it may split the earlier low-conflict view.
        delta = []
        for i, source in enumerate(r.sources):
            c = EvidenceCell(*query, 1, source, Vote.DIFFERENT if i == 0 else Vote.UNKNOWN,
                             'owned later negative epoch')
            delta.append(c)
            await call(i, {'op':'ingest','cells':[c.to_dict()]}, 'later_update')
        await heal('later_repair')
        for c in delta:
            r.add(c)
        later = [await call(i, {'op':'query','left':query[0],'right':query[1]}, 'later_query') for i in range(3)]
        require(all(x['certificate'] == r.certificate(*query) for x in later), 'later semantics')
        reports = [await call(i, {'op':'report'}, 'floor_reports') for i in range(3)]
        floors = common_floor_reports([x['sealed'] for x in reports])
        acks = [await call(i, {'op':'ack','floors':floors}, 'floor_acks') for i in range(3)]
        for i in range(3):
            await call(i, {'op':'compact','floors':floors,'acks':acks,'pending':0}, 'compaction')
        r.compact({(a,b):e for a,b,e in floors},0)
        await heal('floor_repair')
        finals = [await call(i, {'op':'query','left':query[0],'right':query[1]}, 'final_query') for i in range(3)]
        expected_state = r.export_state()
        for answer in finals:
            state = dict(answer['state'],node_id=expected_state['node_id'])
            require(state == expected_state and answer['certificate'] == r.certificate(*query), 'final state/certificate')
        if persistent:
            for i, owner in enumerate(owners):
                saved = owner.replica.export_state()
                reload_started = time.perf_counter_ns()
                await owner.close()
                owners[i] = PersistentMaterializedService(members[i], list(r.sources), r.threshold,
                    list(r.handles), members, owner.snapshot, wire, implementation=implementation)
                require(owners[i].replica.export_state() == saved, 'snapshot restart mismatch')
                ports[i] = await owners[i].start()
                restarts.append(dict(node=members[i],before=saved,
                    recovered=owners[i].replica.export_state(),snapshot=owner.snapshot.name,
                    reload_ns=time.perf_counter_ns()-reload_started))
                answer = await call(i, {'op':'query','left':query[0],'right':query[1]}, 'post_restart_query')
                require(answer['certificate'] == r.certificate(*query), 'restart certificate mismatch')
    except BaseException as exc:
        # Preserve completed benign frames and the failure boundary, even if a
        # case cannot produce an accepted timing row. Never label this a result.
        with gzip.open(out/f'FAILED-{family}-{n}-{seed}-{implementation}.json.gz','wt',encoding='utf-8') as stream:
            json.dump(dict(input_state=instance(family,n,seed).export_state(),events=events,
                peer_frames=peer_frames,restarts=restarts,error_type=type(exc).__name__,
                error=str(exc),accepted=False),stream,sort_keys=True)
        raise
    finally:
        for owner in owners:
            await owner.close()
        service_module.rpc = original_peer_rpc
    elapsed = time.perf_counter_ns()-start
    phase_ns = {phase:sum(e['rpc_ns']+e.get('checker_ns',0) for e in events if e['phase']==phase)
                for phase in sorted({e['phase'] for e in events})}
    if persistent:
        phase_ns['snapshot_reload'] = sum(r['reload_ns'] for r in restarts)
    row = dict(family=family,handles=n,seed=seed,implementation=implementation,
               workflow_ns=elapsed,process_cpu_ns=time.process_time_ns()-cpu_start,
               phases_including_checker_ns=phase_ns,top_level_events=len(events),
               wire_requests=wire.requests,wire_bytes=wire.total_bytes,
               certificate_generations=wire.certificate_generations,
               certificate_ms=wire.certificate_generation_ms,
               volatile_commits=sum(x.volatile_commits for x in owners),
               snapshot_bytes=wire.snapshot_bytes,fsyncs=wire.fsyncs,durable_commits=wire.commits,
               final_state_bytes=sum(len(json.dumps(x.replica.export_state(),sort_keys=True,separators=(',',':')).encode()) for x in owners),
               all_predicates_pass=True,persistence=('file fsync + replace + directory fsync' if persistent
                                                    else 'none: volatile local owners'),
               orderly_restarts=3 if persistent else 0,
               scope='elapsed includes generation/start/update/repair/query/checker/floors/close; excludes raw serialization')
    path = out/f'{family}-{n}-{seed}-{implementation}.json.gz'
    with gzip.open(path,'wt',encoding='utf-8') as stream:
        json.dump(dict(input_parameters=dict(family=family,handles=n,seed=seed),
                       input_state=instance(family,n,seed).export_state(),
                       events=events,peer_frames=peer_frames,finals=finals,
                       restarts=restarts,row=row),stream,sort_keys=True)
    return row


async def run(out, persistent=False):
    require(not out.exists(), 'fresh output directory required')
    out.mkdir(parents=True)
    before = source_binding()
    (out/'source-before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
    (out/'environment.json').write_text(json.dumps(environment(),indent=2),encoding='utf-8')
    probe = await native_persistence_probe(out)
    (out/'native-persistence-probe.json').write_text(json.dumps(probe,indent=2),encoding='utf-8')
    if persistent and (not sys.platform.startswith('linux') or os.name != 'posix' or not probe['acknowledged']):
        (out/'unavailable.json').write_text(json.dumps(dict(
            durable_service_costs_measured=False,
            reason='Linux POSIX runtime and a successful unchanged native durability probe required',
            probe=probe),indent=2),encoding='utf-8')
        raise RuntimeError('durable campaign unavailable; no volatile substitution permitted')
    rows = []
    names = ('indexed','mws_small_table','scanning')
    input_index = 0
    start = time.monotonic()
    for family in ('sparse_cut','dense_cut','low_conflict'):
        for n in (64,128):
            for seed in (1,2):
                offset = input_index % len(names)
                order = names[offset:]+names[:offset]
                input_index += 1
                for implementation in order:
                    rows.append(await case(out,family,n,seed,implementation,persistent))
                    require(time.monotonic()-start < 180, '180-second campaign cap')
    summary = dict(cases=rows,case_count=len(rows),input_graphs=12,
                   raw_event_count=sum(r['top_level_events'] for r in rows),
                   total_wire_requests=sum(r['wire_requests'] for r in rows),
                   total_wire_bytes=sum(r['wire_bytes'] for r in rows),
                   certificate_checks=sum(r['certificate_generations'] for r in rows),
                   total_elapsed_seconds=time.monotonic()-start,
                   comparable_semantics=True,
                   same_persistence_policy=('file fsync + replace + directory fsync in all arms' if persistent
                                            else 'explicitly volatile for all arms'),
                   durable_service_costs_measured=persistent)
    after = source_binding()
    (out/'source-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
    require(before == after, 'owned source changed during workflow campaign')
    summary['source_unchanged'] = True
    summary['order_policy'] = 'input-index-rotated indexed/MWS/scanning; each arm first/middle/last on four of 12 shared inputs; no timing pass threshold'
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k != 'cases'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--persistence',choices=('volatile','durable'),default='volatile')
    args = parser.parse_args()
    asyncio.run(run(args.out,args.persistence == 'durable'))
