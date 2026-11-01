# Process-boundary persistence evidence

This separate correctness cohort runs the actual `Service.dispatch` persistence
API, not a replacement persistence implementation and not a new timing cohort.
It preserves the old process-recovery and MWS/workflow campaigns unchanged.

The retained execution uses one WSL2 Linux/Python 3.12.3 host and native ext4
temporary snapshot paths (`data=ordered`, actual mount options retained). Code
and result storage are outside those runtime snapshot paths. Across two owned
payload sizes and declared prior accepted/absent states, a separate supervisor
kills 54 children with SIGKILL at nine real write/barrier/API-return boundaries.
Six cases expose a genuinely partially written/flushed temporary file. Five
additional actual API controls refuse unregistered sources, invalid vote types,
equivocation, missing floors and an existing but unsealed floor vector.

All 59 cases recovered the exact allowed state, preserved prior acknowledged
cells, and retained every refusal. Six operation acknowledgements were received
by the parent before termination and survived reload; 34 fresh loaded floor acks
returned their complete vectors only after the existing file+directory barrier.
Unacknowledged post-replace updates can be present after reload: they are not
retroactively called acknowledged. The source implementation needed no change.

These are direct API-return receipts carried to an external supervisor over a
local pipe, not TCP client acknowledgement measurements. The wrappers execute
the real write, fsync, replace and directory-fsync operations. Only the partial
write case splits the TextIO write and flushes its prefix before blocking. Other
cuts are before/after calls, not an interruption inside a kernel syscall. The
old/new state oracle is independently encoded as literal cells and JSON states;
it is not an independent human or an independent software population.

No power failure, device-cache persistence, torn sectors, independent machine,
wide-area network, member authentication or crash-consensus guarantee is tested.
The host stays running and can retain cached data after a killed process. A
successful native fsync call plus these recoveries is not a device-durability
certification. Resource observations enforce bounds, not latency/throughput
claims. No old campaign budget or historically excluded timing is reset.

The ordinary deterministic ZIP retains all 141 original files, including empty
and partial temporary files, plus a transport-only per-file SHA/length manifest.
The private originals remain unchanged. Archive size is 110,018 bytes versus
13,406,519 original bytes; this is exact-byte compression, not new observations.
The fixed metadata/order produces identical bytes in a same-runtime rebuild;
cross-zlib-version byte reproducibility is not assumed.

Passive verification after installing the small archive (use a fresh owned
unpack directory, not a publication-tree expansion of the repeated payloads):

```sh
python -B scripts/unpack_process_cutpoints.py --archive results/process-cutpoints-evidence.zip --out /owned/fresh-audit --sha256 3f16b3ad626888137c97418a341e1eb73356664a581530c2240f104531a52fbe
python -B scripts/verify_persistence_cutpoints.py --out /owned/fresh-audit
CIE_PROCESS_CUT_RECORDS=/owned/fresh-audit python -B -m unittest discover -s regressions -p test_process_cutpoints.py -v
CIE_PROCESS_CUT_RECORDS=/owned/fresh-audit python -B -O -m unittest discover -s regressions -p test_process_cutpoints.py -v
```

Do not automatically rerun this cohort from historical reproduction scripts.
A fresh run requires the explicit reviewed protocol and a fresh output path:

```sh
python -I -B experiments/persistence_cutpoints.py --src src --protocol /owned/fresh-audit/protocol.json --out /owned/new-result-path
```

It refuses a non-ext4 temporary filesystem. The declared cumulative campaign
limits are 180 s wall, 90 s aggregate parent+child CPU and a conservative 512 MiB
address-space bound (one child at a time). Those limits are stricter than the
new authorization and do not qualify old timed campaigns. Raw records, partial
temporary bytes, successful returns and failures are never overwritten.
