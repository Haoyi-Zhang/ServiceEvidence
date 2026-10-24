"""Owned counterexample: unchanged partition does not imply bounded retention.

This compares an ordinary union-of-cells log with the floor-aware join, using
the same corrected MWS read function in both arms. No external history is used.
"""
import argparse
import importlib.util
import json
from pathlib import Path

from cie.model import EvidenceCell, Replica, Vote
from cie.mutex_baseline import priority_preserving_mws

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('retention_checker', ROOT/'checker/verify.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def witness():
    original = Replica('owned', ['s0','s1','s2'], 2, ['a','b'])
    for epoch, votes in ((0, ('same','same','unknown')),
                         (1, ('different','unknown','unknown'))):
        for source, vote in zip(original.sources, votes):
            original.add(EvidenceCell('a','b',epoch,source,Vote(vote),'owned retention witness'))
    stale = Replica('stale', original.sources, 2, original.handles)
    for cell in original.cells:
        if cell.epoch == 0:
            stale.add(cell)
    compacted = Replica.import_state(original.export_state())
    compacted.compact({('a','b'):1}, 0)
    # A plain log has no floor/tombstone metadata: replay is ordinary set union.
    plain = Replica('plain-log', original.sources, 2, original.handles)
    for cell in compacted.cells + stale.cells:
        plain.add(cell)
    repaired = Replica.import_state(compacted.export_state())
    repaired.join(stale)
    views = [priority_preserving_mws(r) for r in (compacted,plain,repaired)]
    if not (views[0].components == views[1].components == views[2].components
            and len(plain) == 6 and len(repaired) == len(compacted) == 3):
        raise ValueError('retention witness failed')
    certificates = []
    for replica in (compacted,plain,repaired):
        replica.materialize = lambda r=replica: priority_preserving_mws(r)
        cert = replica.certificate('a','b')
        checker.verify(replica.export_state(), cert)
        certificates.append(cert)
    return dict(provenance='owned constructed two-epoch witness, not an independent real case',
        stale=stale.export_state(), compacted=compacted.export_state(),
        plain_log_replay=plain.export_state(), floor_aware_replay=repaired.export_state(),
        certificates=certificates, retained_cells=[3,6,3],
        equal_partitions=True, equal_certificates=certificates[0] == certificates[1] == certificates[2],
        obligation='retain at most |Sources| cells at acknowledged floor with p=0 after stale replay',
        plain_log_satisfies_retention=False, floor_aware_satisfies_retention=True,
        augmentation='persist and merge floors by maximum; filter obsolete cells; retain sealed floor vectors',
        scope='logical retention counterexample; no durability or performance measurement')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    result = witness()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('retained_cells','equal_partitions','equal_certificates')}))
