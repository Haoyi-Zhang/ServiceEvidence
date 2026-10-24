# Actual Linux durable same-work MWS cohort

This is retained evidence from Ubuntu CI, not a Windows simulation or a fresh
local timing run. `lineage.json` identifies run 40064473190, attempt 1,
job 120784717732, artifact 12548876034 and measured commit
`e9c030e1890b6bd1f3db41694ed131744f40a196`. All 157 original uploaded files
are preserved byte-for-byte: the original cohort is here and its six execution
records are in `execution/`. The ZIP digest is the one printed by the actual
upload job. Archive extraction and local review receipts stay outside this artifact.

## Inputs, raw results and source correspondence

The 36 `*.json.gz` files each retain the actual input state, 48 top-level
application events, 36 nested peer exchanges, 15 state-coupled query answers,
phase timings, final states and three explicit before/recovered reload states.
Twelve generated inputs (three families, 64/128 handles, two seeds) are shared
by indexed, corrected smaller-ID-table MWS and scanning arms. Arm order rotates:
each is first, middle and last on four inputs. All arms use the same service
commit path and 27 mutations/54 fsync calls per case, including ordinary repairs,
a later sealed negative epoch, floor acknowledgements and compaction.

`snapshots/` holds the 108 actual endpoint snapshots. `summary.json` contains
the measured per-case rows; `verified-summary.json` is the original job's
independently reconstructed summary. `native-persistence-probe.json` records
the actual successful native fsync/replace/directory-fsync path, and
`probe/state.json` is its saved snapshot. `environment.json` contains runtime
clocks; `execution/environment.json` holds the richer host/filesystem inventory.

`source-before.json` and `source-after.json` are the original measured hashes
of seven files. `source-preimage/` contains those exact source bytes, checked
against both manifests and the current corresponding implementation before
import. These are scientific source preimages, not a second executable release.
Do not alter the manifests to make changed code appear to be the measured code.
The passive verifier binds to the current corresponding files and refuses a
mismatch. The paper renderer also checks these retained preimages.

## Recheck without rerunning

From the artifact root:

```sh
PYTHONPATH=src python -B scripts/verify_durable_workflow_mws.py --out results/durable-mws-linux
python -B scripts/render_durable_mws.py --output /path/to/paper/tables
python -B scripts/render_durable_mws.py --output /path/to/paper/tables --check
```

These commands open no service sockets and do not rerun measurements. They
reconstruct certificates and complete views, the case matrix and slot order,
phase costs, raw application-frame bytes, source identities and snapshot reloads.
All 540 queries, 108 reloads, 3,024 RPCs, 230,409,192 wire bytes, 972 durable
commits, 1,944 fsync calls and 137,966,625 snapshot-write bytes reconcile.
Snapshot-write bytes are cumulative writes, not final stored footprint.

The primary table reports medians of the two full 128-handle cases per family
and arm. The indexed/MWS medians are close; scanning has the smallest dense-cut
median. No timing pass threshold, uniform ranking or statistical separation
is inferred from these two seeds. Generation, endpoint start/close, updates,
queries, independent checker work, repair, floor coordination and reloads are
included; raw serialization is excluded. Historical Windows pure/volatile
measurements are separate and retain their failed directory-fsync fact.

## Environment and scientific boundary

The captured environment reports Ubuntu 24.04.5, kernel 6.17.0-1022-azure,
CPython 3.12.15, four visible AMD EPYC 9V45 logical CPUs and 16,766,414,848
visible memory bytes. ext4 mount options include `nobarrier,data=writeback`;
the storage medium is unknown. The job applies a 3.5 GiB address-space cap
after environment capture, so the inventory's unset rlimit predates that cap.
Its virtualization field is a detector output, not evidence of bare-metal isolation.

This tests same-host loopback endpoints in one event loop and orderly snapshot
reloads. Successful fsync calls do not establish a hardware persistence guarantee.
No power loss, mid-write crash, independent-process crash, independent-machine
failure, wide-area performance or production deployment was tested in this cohort.
The separate owned abrupt-process campaign retains its own narrower result.
