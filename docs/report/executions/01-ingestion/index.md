# 01 · Ingestion concurrency

- **Why this execution exists** — how throughput and unit cost respond to ingestion concurrency on a Spot pool that scales to zero: how do we configure it?
- **Produces** — the efficiency frontier, the constraint ladder, and the marginal cost per document that report §4 cannot compute itself
- **Expected** — recorded 2026-08-31, before the first run (`git log -S`, commit `bafdc1f`). Tier 1 is the Stage-1 chunker, not TEI. PyMuPDF extraction is single-threaded CPU work and may dominate embedding time by an order of magnitude, while the original design assumed inference would saturate first. Corollary: the unit-cost minimum sits below the throughput knee, driven by warm-up share rather than by any component ceiling
- **Status** — running
- **Plan frozen** — 2026-08-31 · commit `bafdc1f`
- **Givens** — `00-baseline` §2, cited from there

---

## 1 · Plan

### Axis

- **Varied parameter** — KEDA `maxReplicaCount` (N), one value on both ScaledJobs, in `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml`. Fixing one stage while sweeping the other makes the fixed stage the ceiling by construction, and the hypothesis names a stage. The split between them comes from M6 → K7
- **Candidate grid** — N ∈ {4, 24, 50, 100, 125, 175}, revised from the original {4,8,12,16,20,24}. `ingestion-n50-test` (§2 Journal) showed the indexer still at its full N=50 ceiling with no plateau (M5: 50/50 concurrent, against the chunker's 20/50), so the original top of 24 would never have found the indexer's knee. Ceiling raised to 175 against the new Spot quota (192, up from 96), leaving headroom for TEI
- **Sweep order** — coarse to fine: {4, 50, 175}, then refinement points placed by the shape those three produce (`methodology.md` §7). `ingestion-n50-test` already covers the N=50 point
- **Held constant** — image digests, corpus (`zabiullah/pdf-books-collection`, **stratified 100-file / 1.38 GB sample**, drawn from the full 1,041-PDF / 14.52 GB set; Notes), Qdrant collection config, instance types, the TEI trigger, and every row of `00-baseline` §2 Configuration freeze. The config commit moves between points: the swept value lives in Git
- **Not held constant, and measured instead** — TEI replicas. The indexer drives the same autoscaler the query path drives, so TEI scales during a run and its cost above the two-replica floor belongs to this execution → K5
- **Reset between points** — both queues at zero, `apps-compute` at zero nodes, TEI back at 2 replicas, collection recreated
- **Conditions carried to report §2** — bulk-drop arrival, worker packing density of ≈ 3–14 indexer pods per node (computed from frozen requests, `cpu 500m/mem 2Gi` against `c7g.xlarge`/`2xlarge`/`4xlarge` allocatable, memory-bound in every size; never observed live, because `apps-compute`'s actual size mix per point wasn't captured) → K2, and the TEI trigger frozen in `00-baseline` §2

### Window

- **Opens** — first `s3:ObjectCreated`, from the marker the upload script writes · recorded by `run-ingestion-point.py --start-marker`. Upload is outside the system under test
- **Closes** — `apps-compute` at zero nodes **and** TEI back at 2 replicas, plus 5 min (`BUFFER_SECONDS = 300`, `run-ingestion-point.py:75`). Not at queue drain → K1
- **Spacing** — one point per clock hour → K6
- **Excluded from the window** — query load. TEI is shared, and its scale-out would be priced in two executions at once → K5

### Metrics

The register is in `./metrics.md`. PromQL for M1–M9 is in `./data/series.txt` and `./data/guards.txt`, confirmed names only, dry run clean 2026-09-01 (`ingestion-n50-test`).

### Validity

| Condition | Action | Ref |
| :--- | :--- | :--- |
| image digests, corpus or `00-baseline` §2 differ from the other points | exclude | |
| reset did not run: collection not recreated, or TEI above 2 at open | exclude | K5 |
| the window shares an hourly CUR bucket with another point | exclude | K6 |
| M1 does not fall steadily | not trusted; the wall time behind D22 describes a stall | |
| M5 disagrees with N | file the point under M5, both numbers in the matrix | K7 |
| a node was lost during the window | re-run, or mark ᴱ and drop it from the curve fit | K1 |
| R21 differs from the frozen corpus count | re-run; the denominator lies | |
| split cost allocation returns no rows for the point's pods | keep the cost row, drop the M12 decomposition | K5 |
| M8 non-zero | the cost row stands; the memory guardrail it fed is void | K3 |

Averaging an excluded point back in silently is not a third option.

---

## 2 · Journal

One invocation per point: uploads the corpus, times the window, exports, resets the cluster for
the next point. Does not read cost. Exit codes and what to do with each are in
`run-ingestion-point.py --help`.

```bash
../../scripts/run-ingestion-point.py --run ingestion-n04 --n 4 --doc-count 100
```

Before `watch`, the script launches the corpus upload itself and uses that launch instant as the
window start, so no marker file is needed. After export, it runs
`prepare-cluster-for-ingestion.py` (S3 clean → SQS purge → kill chunker/indexer Jobs → reset
Qdrant → wait for `apps-compute` at zero and TEI at floor). That leaves the cluster ready for the
*next* point. Each point opens on whatever the previous point's reset left behind, so the very
first point needs a manual reset, described after the flag table.

| Flag | Effect |
| :--- | :--- |
| `--no-prepare` | skip the cluster reset after export; reset by hand, or rely on organic drain |
| `--prepare-timeout <s>` | override the reset's wait-for-floor timeout (default 900s) |
| `--no-upload` | upload out of band; falls back to `--start`/`--start-marker`, else an inferred, poll-granularity start |
| `--upload-dir` / `--upload-prefix` | a different corpus than the default sample |

`prepare-cluster-for-ingestion.py` also runs stand-alone. Run it once before the first point:

```bash
../../scripts/prepare-cluster-for-ingestion.py             # clean, kill, reset, wait for drain
../../scripts/prepare-cluster-for-ingestion.py --no-wait   # fire and return
```

The cost pass runs once for the whole campaign, at least 48 h after the last point, over the
windows recorded in R19 → K6:

```bash
../../scripts/aws-cur-report-export.py --data s3://simple-rag-cur-reports-883f615c/cur2/simple-rag \
                            --start ⟨window start⟩ --hours 1 \
                            --tag feature=simple-rag --split --format csv
```

One invocation per point window. The serving pool idle rate from `00-baseline` §2 is subtracted
before the figures land in `./data/frontier.csv`.

### Run ledger

| #  | Point              | Window UTC | Commit | Outcome | Signal | Exported | Cost read |
|:---|:-------------------| :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | ingestion-n04      | not run: low end of the original grid, before the plan was revised to the 10/25/50/75/100/125 grid actually swept | | | | | |
| 02 | ingestion-n24      | not run, same reason as `n04` | | | | | |
| 03 | ingestion-n50-test | 2026-09-01T12:51:46Z → 13:43:14Z | `cacb7f5` (dirty) | ok; two node-loss warnings, reclassified benign (Notes) | indexer at ceiling, M5 50/50 concurrent · chunker headroom, 20/50 ᴿ | ✓ (recovered by hand, `export-metrics.py --force`) | — |
| 04a | ingestion-n100-sticky | 2026-09-03T15:19:31Z → 15:57:48Z | `9c280655cea7` | superseded: sticky TEI routing (Notes); re-run after the fix | indexer at N ceiling (M5 100/100) but M6=0.146, not CPU-bound ᴱ | ✓ (8/9, M8 gap) | — |
| 04 | ingestion-n100     | 2026-09-03T16:24:23Z → 17:05:31Z | `cfa0ab7` (dirty) | ok, post-fix; wall-clock and cost nuance in Notes | indexer at N ceiling, M5 100/100 · chunker headroom 20/100 · TEI peak ~23 replicas ᴿ | ✓ (8/9, M8 gap, same GC race as n100-sticky) | — |
| 05 | ingestion-n125     | 2026-09-04T14:00:58Z → 14:39:25Z | `15d43d5` (dirty) | ok; closed by hand after the runner process was killed externally (Notes) | indexer at N ceiling, M5 125/125 · chunker headroom 20/125 · TEI peak 26 replicas ᴿ | ✓ (8/9, M8 gap) | ✓ CUR, see Notes under #08 |
| 06 | ingestion-n75      | 2026-09-04T15:06:08Z → 15:48:59Z | `1b5ad91` (dirty) | ok; off-plan refinement point (Notes) | indexer at N ceiling, M5 75/75 · chunker headroom 20/75 · TEI peak 16 replicas ᴿ | ✓ (8/9, M8 gap) | ✓ CUR, see Notes under #08 |
| 07 | ingestion-n50      | 2026-09-04T16:01:22Z → 16:45:23Z | `005914d` (dirty) | ok, post-fix, fresh cluster instance (Notes) | indexer at N ceiling, M5 50/50 · chunker headroom 20/50 | ✓ (8/9, M8 gap) | ✓ CUR, see Notes under #08 |
| 08 | ingestion-n25      | 2026-09-04T17:00:55Z → 18:02:39Z | `1d87721` (dirty) | ok; the NAT methodology bug was found here (Notes) | indexer at N ceiling, M5 25/25 · chunker headroom 20/25 · TEI peak 4 replicas | ✓ (8/9, M8 gap) | ✓ CUR, see Notes under #08 |
| 09 | ingestion-n175     | not run: top of the original grid, dropped once the trend proved monotonic downward through n25 | | | | | |
| 10 | ingestion-n10      | 2026-09-05T10:27:09Z → 12:39:36Z | `4e15a2c` (dirty) | non-standard: new cluster, corpus reloaded to repopulate Qdrant for `02-inference`. The script timed out (exit 4, 1h30m max wait), and the point was closed by hand after manual polling confirmed convergence + buffer (Notes) | indexer at N ceiling, M5 10/10 · **chunker also at N ceiling, 10/10** (first point where N < chunker's own ~20 corpus cap) · TEI peak 3 replicas | ✓ (8/9, M8 gap) | ᴰ, floor only; 5/11 nodes unpriced (Notes) |

`Exported` is filled when the run ends. `Cost read` is filled by the cost pass, days later, and
a blank there after the pass ran is a lost cost row rather than a lost point.

### Notes

**Corpus provisioning** — 1,041 PDFs (14.52 GB) uploaded to the raw-docs bucket in 387 s
(37.6 MB/s) via `download-pdf-books-dataset.py` + `upload-dir-to-s3.py` (16 workers, 16 MB
multipart threshold). Throughput was bound by the operator's home uplink rather than by S3 or
the scripts' concurrency; the HF download side ran at a comparable ~34 MB/s. This is not a
system-under-test figure and is excluded from every point's window (§1 Window: upload is outside
the system under test).

**Corpus resized to a stratified sample** — the full corpus made a five-point sweep with resets
impractical. 100-file / 1.38 GB sample (~9.5%), stratified over 10 size deciles at seed 42 so
the size-mix driving PyMuPDF time matches the full corpus (13.77 MB/file mean vs. 13.96 MB).
Manifest: `../../../../tmp/ingest-sample-manifest.tsv` · files: `tmp/ingest-sample/` (untracked).

**Decision after the coarse pass** — no clean "coarse pass, then two refinement points" happened.
`n50-test` (off-plan, validation) came back clean and was kept as a real point; `n100` followed,
then `n125` (top of grid). The downward-sloping cost trend from `n100`→`n125` prompted one
off-plan refinement point, `n75`, to see the shape between them. It was a single point added live
in response to a trend nobody had predicted, not two points chosen from a plan. `n25` and `n10`
came later for other reasons (closing the low end, then reloading Qdrant for `02-inference`), and
were not planned refinement either. The Run ledger and each point's Notes give the reason for
each.

**#03 ingestion-n50-test** — run off-plan (N=50 wasn't in the original grid) to validate the
automation end to end before the real sweep, and kept as a grid point afterwards because it came
back clean. Two things looked like they would invalidate it and didn't:

- *Two "node left" warnings* (`ip-10-0-11-186`, `ip-10-0-12-180`, both at 13:10:14Z, logged
  while combined queue depth was 1427). Checked against M4: neither node had a single chunker or
  indexer container scheduled on it during the whole window. Karpenter's
  `WhenEmpty`/`WhenEmptyOrUnderutilized` consolidation only disrupts an already-empty node, so
  these were ordinary teardowns of nodes that happened to be idle while other nodes still had
  backlog, and no work was lost. `run-ingestion-point.py`'s detection checked system-wide queue
  depth instead of the node's own workload. Fixed (`labkit.pods_by_node` + `FORCED_REASONS`,
  `SpotInterrupted`/`TerminatingOnInterruption`/`InstanceStopping` only), so future points
  aren't flagged for this by mistake.
- *Export gap* — both local port-forwards (Prometheus, Qdrant) died around minute 27 of the
  51m28s window (`labkit.PortForwards` had no health check). `run-ingestion-point.py` correctly
  refused to wipe after the export failure. The export was recovered by hand with the exact
  command the script printed, and 8/9 refs came back clean (M8/OOMKilled empty is a real zero;
  nothing was OOM-killed). Also fixed (`PortForwards.ensure_alive()`, called from the watch loop
  and before R21/export).

R21 confirmed 84,018 points from the 100-file sample post-recovery.

**#04a ingestion-n100-sticky** — TEI load was badly imbalanced across replicas mid-run
(`te_queue_size` in the hundreds on some pods and zero on others at the same moment), despite the
earlier headless-Service fix (§1 of that session's postmortem). The root cause is not the
Service, and it was confirmed in code rather than inferred.
`huggingface_hub.utils._http.get_session()` returns a process-wide singleton `httpx.Client`
(`apps/indexer/.venv/.../huggingface_hub/utils/_http.py:335`, "shared between all calls"), and
`apps/indexer/src/main.py` builds the Haystack pipeline once per pod and reuses it across the
pod's whole `while not graceful_exit` SQS-poll loop. One indexer pod's entire embedding traffic
therefore rides a single TCP connection for its lifetime, pinned to whichever TEI backend
Cilium's L4 hash picked on first connect. TEI replicas that scale out mid-run get no traffic
until a fresh connection happens to land on them.

**Ceiling check, from the exported data (M5/M6):** indexer M5 = 100/100 (at the concurrency
ceiling, matching N set) but M6 = 0.146, only 14.6% of its CPU budget (workers × window × limit).
Pods that sit at their full concurrency ceiling while far from CPU-bound are blocked on a slow
dependency rather than computing. That fits the sticky TEI routing finding: 6 of 19 TEI replicas
carried hundreds of queued requests while 13 sat idle. chunker M5 = 20/100, M6 = 0.012,
unaffected, with the same headroom as `n50-test`.

**Decision: this run does not stand as a grid point.** The concurrency ceiling is real (M5
matches N), but the routing artifact suppressed throughput at that ceiling, so `$/run` and
`docs/min` here are pessimistic compared with N=100 once TEI load is spread across replicas.
Renamed to `ingestion-n100-sticky` (ledger #04a) to free the id `ingestion-n100` for a clean
re-run. This run's data (window `2026-09-03T15:19:31Z → 15:57:48Z`, commit `9c280655cea7`) stays
here as the documented cause and is not averaged in. Provisional cost estimate
(karpenter/EC2/CloudWatch reconstruction, not CUR):
`./data/ingestion-n100-sticky.cost-estimate.json`, `D24 ≈ $1.85/run`, inflated for the same
reason (nodes stayed up longer waiting on TEI instead of computing).

Fix deployed (`32365dc`, `apps/indexer/src/main.py`). Partway through that session,
`argocd-image-updater` stopped considering the `indexer` alias for updates, for an undiagnosed
reason; the problem survived a clean pod restart, so it wasn't a cache or backoff issue. Resolved
by hand by pointing `deploy/k8s/apps/indexer/.argocd-source-indexer.yaml` straight at the built
digest, the same workaround `postmortem.md` §11 used before. `ingestion-n100` was re-run under
the fixed image.

**M8 gap, same run** — the export also came back with `M8` (OOMKilled) empty
(`export-metrics.py` exit 2, correctly not reported as a zero). Root cause: by the time export
ran, all 6 retained Job objects (`successfulJobsHistoryLimit`/`failedJobsHistoryLimit` = 3+3) had
no pods left. `kube_pod_container_status_last_terminated_reason` lives on the Pod object, and
orphaned-pod GC removes the Pod once its node is gone, regardless of the Job's history limit.
`apps-compute`'s `consolidateAfter` (5m rather than the 30s frozen in `00-baseline`, a divergence
flagged there too) meant nodes began tearing down well before export ran. Exported anyway with
`export-metrics.py --force`, which writes the file despite the gap (`--force` means "overwrite",
not "ignore the gap"). 8/9 refs are good. M8 is a documented instrumentation gap for this run,
not a claimed zero, and worth revisiting before a point where an OOM signal matters. The same gap
recurred on `#04 ingestion-n100` (the same GC race, not a new bug) and was also `--force`d.

Chasing this turned up two more instrumentation bugs, both fixed. The Qdrant checks in
`run-ingestion-point.py` and `prepare-cluster-for-ingestion.py` treated `HTTP 404` (collection
doesn't exist, the correct state right after a delete-based reset) as "unreachable", which failed
preflight on a clean cluster. Both now treat 404 as `points == 0`.

**#04 ingestion-n100** — real point, post-fix (`32365dc`, deployed by hand through
`.argocd-source-indexer.yaml` after `argocd-image-updater` stopped picking up the `indexer`
alias; undiagnosed, and it survived a clean pod restart). R21 = 84,018, the same as the sticky
run (same corpus). `te_queue_size` and per-pod CPU were checked live during the run. Settled TEI
replicas no longer sit at zero for their whole life as they did before the fix: a new pod ramps
from ~0.5 to ~2.4 cores within about a minute of joining.

**The aggregate numbers are not a clean win:**

| | `n100-sticky` | `n100` (fixed) | Δ |
| :--- | :--- | :--- | :--- |
| Window | 2298 s (38m17s) | 2468 s (41m08s) | **+7.4%**, longer |
| `M10` compute $ | $1.3808 | $1.2877 | **−6.7%**, cheaper |
| `M11` serving gross $ | $0.5684 | $0.8698 | **+53.0%**, much more |
| TEI peak replicas | ~19 | ~23 | higher |

Compute cost dropped, consistent with indexer pods spending less time blocked on TEI. Total
wall-clock time went up, though, and TEI scaled to more replicas (peak ~23 against ~19). A
plausible reason: with routing fixed, the indexer drove concurrent demand across all TEI backends
instead of saturating a few while most sat idle, so *aggregate* demand on TEI, and TEI's own
scale-out, rose. The fix solved the fairness and attribution problem, confirmed live rather than
inferred from an aggregate, but it did not clearly reduce this run's `$/run` or wall-clock time.
Left as an open question for Retro. Provisional estimate with the full breakdown:
`./data/ingestion-n100.cost-estimate.json` (`D24 ≈ $1.76/run` against the sticky run's `$1.85`,
too close for one pair of runs to show whether the fix helps cost).

**#05 ingestion-n125** — started at the `14:00:00Z` hour boundary on purpose (K6: keep this
point's window inside its own UTC clock hour). The cluster was reset and re-frozen ahead of time
on a new cluster instance after teardown (`tmp/post-mortem/postmortem-2026-09-03-...md` §11).
`argocd-image-updater` was not involved this time: `root-bootstrap`/`rag-apps` synced straight to
the branch tip on first bootstrap. `maxReplicaCount` raised to 125 on both the `chunker` and
`indexer` ScaledJobs.

The queue drained cleanly, `apps-compute` reached zero and TEI returned to floor. The runner
(`run-ingestion-point.py`) was already holding the close buffer (`nodes=0, tei=2` since
`14:34:25Z`, needs 300s) when its background process was killed externally. It was not a script
crash: the harness reported a `killed` status, most likely a session interrupt. After confirming
the cluster had not drifted (R21 already 84,018, `apps-compute` still at 0), `14:39:25Z` was taken
as the close time and `export-metrics.py --force` / `prepare-cluster-for-ingestion.py` were run by
hand. That produces the same data the script would have, assembled manually.

R21 confirmed 84,018: same corpus, same count, third run in a row. M5: indexer 125/125 (full
ceiling, tracking N exactly, the same signature as `n50-test` and `n100`), chunker 20/125 (the
same demand ceiling as every earlier run; four points now show that the chunker's cap comes from
the corpus, not from `maxReplicaCount`). TEI peaked at **26** replicas, up from `n100`'s 23. That
matches the roughly linear scaling the indexer architecture analysis predicted (not yet
CPU-bound, and below TEI's ceiling of 30).

Cost estimate (karpenter/EC2/CloudWatch, same method as `n100`):
`./data/ingestion-n125.cost-estimate.json`. `M10` compute $1.44 (up from `n100`'s $1.29), `M11`
serving gross $0.98 (up from $0.87), `D24 ≈ $1.97/run`. Both cost lines rose with N this time,
unlike the `n100-sticky → n100` comparison, where compute and serving moved in opposite
directions. It is still one measurement per N, with the same statistical caveat.

**Live incident during prep** — the `argocd.argoproj.io/compare-options: ServerSideDiff=true`
annotation, added in the previous session to stop qdrant's self-heal loop
(`tmp/post-mortem/postmortem-2026-09-03-...md` §4), made this cluster's `gitops-engine` (v0.7.1)
panic on at least some apps. The `argocd-application-controller` logs show `Recovered from panic:
invalid memory address or nil pointer dereference` in `diff.removeWebhookMutation`. The panic is
caught per app, but that app's reconcile silently aborts for the cycle. This, and not
`argocd-image-updater` (the suspect during the `n125` prep), was blocking `indexer`/`chunker` from
picking up new commits. The annotation was reverted in git, but an ArgoCD ApplicationSet only adds
or updates annotations from its template and never prunes removed ones, so the revert didn't
clear it from the 9 Applications already generated. Each one had to be patched with
`kubectl patch --type merge` (`{"metadata":{"annotations":{"...
compare-options":null}}}`) to remove it. Clean afterwards (0 panics/minute). The qdrant
self-heal loop the annotation was meant to fix is left alone: it is cosmetic, disrupts no pods,
and isn't worth another attempt until the fix is tested against this cluster's ArgoCD version.

**#06 ingestion-n75** — off-plan, added after `n125`. Both `n100` and `n125` showed the indexer
well below its CPU ceiling (M6 ~12-17%) and TEI below its replica ceiling (23/30, 26/30), but the
shape between 50 and 100 was unknown, since `n50-test` and `n100` bracket a wide gap. N=75 filled
it in before committing to `n175`.

R21 = 84,018, the fifth point in a row with the identical count. M5: indexer 75/75 (full ceiling,
the same signature as every other point), chunker 20/75, the **fifth consecutive confirmation**
that the chunker's ceiling comes from the corpus (fixed at 20 regardless of `maxReplicaCount`).
TEI peaked at 16, continuing the roughly linear relationship with N (16 → 23 → 26 for
N = 75 → 100 → 125).

**First look at the cost trend, three points (75/100/125)** — `$/1M docs` rose **monotonically**
with N ($15,623 → $17,613 → $19,657), the opposite of the U-shaped curve §1 Expected predicted.
The four-point table under #07 supersedes this one (same numbers, plus n50). Each N still had a
single run at this stage, with the same caveat as the `n100-sticky → n100` comparison, but three
points agreeing on a direction was the first sign the trend might hold.

**#07 ingestion-n50** — a fresh point (not a reuse of `n50-test`, #03) to complete the trend
below `n75`. R21 = 84,018, the sixth point in a row with the identical count. M5: indexer 50/50
(full ceiling), chunker 20/50, the sixth consecutive confirmation of the corpus-driven chunker
cap. Also seen live: two `tei-embeddings` pods sat `Terminating` for 5–12 min mid-run. The cause
was `apps-serving`'s `consolidationPolicy: WhenEmptyOrUnderutilized` evicting pods to repack
nodes as TEI scaled down (`Evicted pod: Underutilized` in pod events); the pod object then stayed
stuck until orphaned-pod GC caught up with the node's teardown. It is the same mechanism as the
`M8` gap with a different symptom. No data was lost (SQS redelivers); it only added noise and
latency late in the window.

**Cost trend, four points: the monotonic pattern holds down to N=50.**

| N | `M10` compute | `M11` serving gross | `D24` $/run | `D25` $/1M docs |
| :--- | :--- | :--- | :--- | :--- |
| 50  | $0.98 | $0.50 | $1.28 | $12,750 |
| 75  | $1.19 | $0.69 | $1.56 | $15,623 |
| 100 | $1.29 | $0.87 | $1.76 | $17,613 |
| 125 | $1.44 | $0.98 | $1.97 | $19,657 |

The four points move in one direction with no reversal, and the U-shape `§1 Expected` predicted
appears nowhere in the tested range (50–125). Either the minimum sits below 50 (untested; the
original grid's next-lowest point is `N=24`), or this range has no U-shape at all and lower N is
cheaper per document throughout, at the cost of wall-clock time. There is still one run per N
(no repeated trials, no error bars), but four agreeing points are a much stronger signal than the
two-point comparison under #04. Before writing the Finding in §3, pull `docs/min` and `N reached`
across all four: this section tracked only dollar figures, so "cheaper" hasn't yet been checked
against "how much slower".

**#08 ingestion-n25** — extends the trend one point lower. R21 = 84,018 again, the seventh point
in a row with the identical count. M5: indexer 25/25 (full ceiling), chunker 20/25, the seventh
consecutive confirmation of the corpus-driven chunker cap. TEI peaked at 4 replicas (M9), and the
2 `apps-serving` nodes already up at the floor absorbed the burst for the whole window. No extra
serving node was billed, so `D23` is correctly $0 here.

**NAT methodology bug found here, affecting every earlier point** — `M14` for
n50/n75/n100/n125 was computed from `AWS/NATGateway`'s `BytesInFromSource` metric alone, the
outbound leg (pods' requests leaving through NAT). AWS bills NAT data processing on *both* legs of
a flow, and the inbound leg (`BytesInFromDestination`, responses coming back through NAT) was
never queried. For an ingestion point, the inbound leg is dominated by `chunker`/`indexer`
container image pulls from `ghcr.io` each time Karpenter boots a fresh `apps-compute` node.
`ghcr.io` is an external registry with no VPC endpoint, unlike ECR, so every pull is billed NAT
traffic. Confirmed on n25's own window: a 5-minute CloudWatch profile puts >99% of the window's
`BytesInFromDestination` in the first 10 minutes (17:00–17:10Z), exactly the node-bootstrap
window in `karpenter-cost-estimate.py`'s node list (first `apps-compute` nodes seen
17:02:55–17:04:55Z). After that the background trickle is ~0.01–0.03 GB / 5 min.

Recomputed both directions from raw CloudWatch bytes:

| Run | old `M14` (outbound leg only) | corrected `M14` (both legs) | ratio |
| :--- | :--- | :--- | :--- |
| n50 | $0.0163 | $2.6080 | ×160 |
| n25 | $0.0109 (would have been, same old method) | $1.1989 | ×110 |

n25's ledger and `./data/ingestion-n25.cost-estimate.json` use the corrected figure: `D24` =
$0.875 (`M10`) + $0 (`D23`) + $0 (`M13`) + $1.199 (`M14`) = **$2.074/run, $20,739/1M docs**.
That is already higher than every earlier point's *reported* $/1M docs, although N=25 was the
lowest N run so far. At low N the image-pull NAT cost is a larger share of a smaller run total, so
correcting it consistently may flatten or invert part of the monotonic trend.

A same-day spot-check on n50 alone (CloudWatch bytes, before CUR was available) moved its `D24`
from $1.275 to $3.867/run, over 3× the reported figure. That gap made it worth pulling real CUR
numbers for all four points immediately instead of waiting; the result follows.

**CUR actuals pulled (2026-09-05, `00-baseline` §2's source of record). They supersede the
estimates in these Notes, not only `M14`.** CUR delivered a batch covering all of `2026-09-04`,
which contains all four points. The query ran directly against
`s3://simple-rag-cur-reports-883f615c`, grouped by the hour of `line_item_usage_start_date` (each
point occupies a distinct UTC hour by design, K6), by `resource_tags['user_karpenter_sh_nodepool']`
for compute and serving, and by the NAT gateway's `line_item_resource_id`
(`arn:...natgateway/nat-08e283a51761f1e9b`) for NAT. NAT turned out to bill under product code
`AmazonEC2` rather than the assumed `AmazonVPC`, and to carry one more line item
(`EUC1-DataTransfer-Regional-Bytes`) that neither the original nor the corrected CloudWatch-based
`M14` had priced.

| N | reported `D24` | CUR compute | CUR NAT (both legs + regional transfer) | CUR marginal (compute+NAT+SQS+S3) | ratio | `D25` compute+NAT only, $/1M docs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 125 | $1.97  | $2.0069 | $5.9919 | **$8.00<!--FM26-->** | ×4.1 | $79,999 |
| 75  | $1.56  | $1.5446 | $4.0939 | **$5.64<!--FM27-->** | ×3.6 | $56,396 |
| 50  | $1.275 | $1.2613 | $2.8776 | **$4.14<!--FM28-->** | ×3.2 | $41,400 |
| 25  | $0.886 | $1.0916 | $1.3823 | **$2.48<!--FM29-->** | ×2.8 | $24,750 |

`CUR marginal` = tagged `apps-compute` cost + the NAT gateway's full line-item set for that hour +
SQS + S3 (both ~$0, covered by the free tier at this volume). It excludes `apps-serving` on
purpose: the underlying query shows it gross next to compute ($1.20/$0.90/$0.68/$0.39 for
125/75/50/25). `D23` (TEI above floor, net) is measured separately as of 2026-09-19 and added in
the Matrix, so this table's last column sits below the Matrix's `$/1M docs` by exactly
D23 × 10,000 at every point. It also excludes ~$0.9–1.15/hour of `baseline_other` (EKS control
plane, two core nodes (`r7g.large`, `t3.large`), ELB, CloudWatch, KMS), which appears in every
hour regardless of N and is fixed cluster overhead rather than marginal to any one point.

Two things confirmed, one thing newly found:
- **Direction holds** — the monotonic rise with N is real, not an artifact of the `M14` method.
- **Magnitude was badly understated** — even after the 2026-09-04 NAT-bug fix, real `D24`/`D25`
  are 2.8×–4.1× the reported figures. The gap grows *with* N and is worst at the top of the
  tested range, so the reported figures were furthest off in exactly the high-N, many-node case.
- **Compute was also off**, independently of NAT. Reading `describe-spot-price-history` at node
  start time (`karpenter-cost-estimate.py`'s method) comes out 15–25% below what CUR billed for
  the same instances, because Spot price can move between the snapshot and the charged rate. The
  estimator's docstring says it doesn't replace CUR, and this is the concrete gap that caveat was
  about.

Re-pulled 2026-09-07, past the 48h guard: unchanged for all four points, with no credits or
true-ups. This table is final.

**#10 ingestion-n10** — off-plan, run on a freshly bootstrapped cluster (2026-09-05) for a reason
no earlier point had. `02-inference`'s precondition needs a loaded Qdrant collection, no
snapshot/restore mechanism existed (`00-baseline`'s "restored from the 01-ingestion snapshot" was
never built; the `vector-db-historic` fix at the end of this note covers it), and the cluster's
Qdrant was empty. Reloading the same 100-file corpus doubles as an off-plan grid point below n25,
so it is recorded here.

`run-ingestion-point.py` timed out (exit 4, "did not converge"; the script exported and wiped
nothing) at its default 1h30m max wait. The queue was still draining, not stuck: SQS stage-2
depth fell from 709 to 639 over the 15 minutes around the timeout. The point was watched by hand
from there. It converged at `12:34:36Z`, held the 300s buffer clean, and was then exported and
priced manually. The window came to **2h12m**, more than 4× any earlier point's wall time, at
less than half n25's N. It is the clearest wall-clock evidence so far that low N trades time for
cost.

M5: chunker 10/10, indexer 10/10, the **first point where the chunker shows no headroom**. Every
earlier point (25 through 125) had the chunker capped at ~20 regardless of `maxReplicaCount`, read
as a corpus-driven ceiling. N=10 sits below that ceiling, so the chunker fills to N. That supports
the corpus-cap reading: the chunker's appetite is still ≥10, and this time `maxReplicaCount` was
the binding limit.

The same-day provisional estimate was only a floor: 5 of 11 nodes seen in the window resolved to
`instance_type: "?"` in `karpenter-cost-estimate.py`. They were short-lived, replaced early, and
past EC2's ~1h post-termination `describe-instances` visibility by the time pricing ran.
`apps-serving` also churned through 5 distinct node IDs against a floor of 2, so `D23` was left
unresolved. A CUR read on 2026-09-07 replaced the estimate with $41,624/1M docs, and measuring
`D23` on 2026-09-19 brought it to **$44,707<!--FD76-->/1M docs**. The §3 Matrix
gives the number and explains why it breaks the otherwise clean N-vs-cost trend.
`./data/ingestion-n10.cost-estimate.json` has the provisional breakdown,
`./data/ingestion-n10.cur-actual.json` the CUR one.

**Fix landed alongside this point**: `02-inference`'s Qdrant-restore precondition had no
implementation; no snapshot/restore script existed anywhere in the repo. A live snapshot of this
point's collection was taken through Qdrant's REST API (`POST /collections/simple-rag/snapshots`)
and uploaded to a new bucket, `s3://vector-db-historic/qdrant-384-1gb-snapshot` (496 MB, 84,018
points). It is the first snapshot this project has taken; the CronJob in
`deploy/k8s/platform/qdrant/qdrant-backup-cronjob.yaml` assumes one exists. Restore is still manual
(download + Qdrant's snapshot-recovery API) and not scripted, which doesn't block anything.

### Close

- [x] Saturation identified, or headroom confirmed at the top of the grid: none found by resource signature (§3 Saturation). The constraint is architectural (the indexer's sequential one-in-flight TEI design), and N reached tracked N set exactly through N=125 with no sign of flattening.
- [x] Cost pass run at least 48 h after the last point (2026-09-07): unchanged for N=25/50/75/125, first real read for N=10. The re-run after month close is still open.
- [x] M12 decomposition present (2026-09-09, §3 M12 table): split-cost data for every point's hour bucket, pulled directly from the CUR parquet. It covers the EKS instance-hour slice only, not the full `$/run`. D28/D29 are still declared not made, each for its own reason (§3).
- [x] TEI peak replicas recorded at every point, and D23 computed: measured from CUR on 2026-09-19 for all five points (Matrix, `figures.yaml` group `d23`). No point declares zero any more; `n25` is $0.0075<!--FM24-->, the smallest.
- [x] `M14` re-pulled with both `AWS/NATGateway` byte-direction legs, then superseded entirely by CUR actuals (2026-09-05); Notes under #08.
- [x] CUR-based `D23` (TEI above floor, net): closed 2026-09-19. The missing piece was the floor rate itself, not the gross. Each run day's own resting hour supplies it ($0.37940<!--FM1-->/h on 09-04, $0.18480<!--FM13-->/h on 09-05), so the two-replica floor now nets out per point.
- [x] Re-checked the CUR pull after 48h (2026-09-07): N=25/50/75/125 unchanged from the ~24h read, no credits or true-ups.
- [ ] M18 read at the highest-N point and compared against D30, or the comparison declared not made.
- [x] Collection point count written back into `00-baseline` §2 Envelope: 84,018, done 2026-09-09.
- [ ] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ.
- [x] Outcome compared against Expected in Retro, inversion included (Retro, first bullet).

---

## 3 · Results

**Finding** — Throughput never plateaus in the tested range (N=10–125): docs/min rises
monotonically with N throughout (0.76 → 2.60), so no saturation point exists to name as a knee in
the throughput sense the plan expected. Unit cost never bottoms mid-range either: `$/1M docs`
also rises monotonically with N, so the cheapest tested point is the lowest valid one (N=25). The
U-shaped cost curve `§1 Expected` predicted did not appear. More concurrency bought throughput at
every step, at a steadily worse cost per document → report §3.3

### Matrix

`N reached` is M5's time-weighted mean over the whole window (queue-drain and buffer tails pull
it well below peak), with the peak in brackets. Cost columns for N=25/50/75/125 are CUR actuals,
**re-pulled 2026-09-07 (>48h after the last point) and unchanged from the 2026-09-05 read**, so
the 48h guard is cleared with no revisions, credits or true-ups. N=10's CUR actual was first
pulled on 2026-09-07; it ran a day after the other four, and no earlier CUR delivery covered it
(`./data/ingestion-n10.cur-actual.json`). `TEI $` (D23) is measured ᴿ for all five points as of
2026-09-19 (`docs/report/figures.yaml`, group `d23`). Each point owns one clock hour, confirmed by
matching CUR compute against the per-point figures below to the cent, so D23 is that hour's
`apps-serving` gross (instances, cross-AZ transfer and root volumes) net of the day's resting
rate. The two days rest differently: 09-04 held 2 × c7i-flex.2xlarge Spot at $0.37940<!--FM1-->/h, 09-05
held c5.xlarge + c6a.xlarge at $0.18480<!--FM13-->/h, so each point is netted against its own day. `n10`'s
last hour overlaps `02-inference`'s campaign window by $0.0441.

| Run | N set | N reached | TEI peak | Docs/min | Wall time | Compute $ | TEI $ | Other $ | $/run | $/1M docs | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #10 | 10 | 9.0 (10) | 3 | 0.76 | 132.5 min | $1.55 | $0.31<!--FM25--> | $2.61 | $4.47<!--FD71--> ᴰ | **$44,707<!--FD76-->** ᴰ | chunker *also* at N ceiling; the one point below the corpus's ~20-concurrent cap |
| #08 | 25 | 19.5 (25) | 4 | 1.62 | 61.7 min | $1.09 | $0.01<!--FM24--> | $1.38 | $2.49<!--FD70--> ᴰ | $24,875<!--FD75--> ᴰ | none; indexer at ceiling, no resource pegged |
| #07 | 50 | 32.6 (50) | 10 | 2.27 | 44.0 min | $1.26 | $0.29<!--FM23--> | $2.88 | $4.43<!--FD69--> ᴰ | $44,335<!--FD74--> ᴰ | none |
| #06 | 75 | 40.5 (75) | 16 | 2.33 | 42.9 min | $1.54 | $0.52<!--FM22--> | $4.10 | $6.16<!--FD68--> ᴰ | $61,573<!--FD73--> ᴰ | none; the "waste boundary": +39% cost for +2.6% docs/min over N=50 |
| #05 | 125 | 63.5 (125) | 26 | 2.60 | 38.5 min | $2.01 | $0.82<!--FM21--> | $5.99 | $8.82<!--FD67--> ᴰ | $88,161<!--FD72--> ᴰ | none |

N=10 (#10) breaks the otherwise clean monotonic N-vs-cost trend: $44,707<!--FD76--> sits just above N=50's
$44,335<!--FD74--> instead of below N=25's $24,875<!--FD75-->, where the throughput trend alone would put it. With D23
measured rather than estimated, N=10 is now the second most expensive point of the five, not the
third. The
script's timeout and the manual recovery did not inflate the number, as was first assumed. NAT
was re-pulled directly (2026-09-09, `./data/nat-by-window.json`) and split into `Hours` (the flat
per-hour NAT Gateway charge) and `Bytes` (data processing, ~98% of the total). Two honest
denominators exist, and they disagree on the fine ordering. CUR is hourly (`00-baseline` flags
this as the limit of its resolution), so dividing a bucketed cost by the *number of hour buckets
touched* (N=10: $0.87/h) and by the run's *actual* wall time (N=10: $1.18/h) give different
answers on whether N=10 sits above or below N=25 ($0.72/h and $1.39/h the same two ways). This
data can't resolve it more precisely.

What **does** survive both conventions: N=10 and N=25 sit in the same order of magnitude either
way (0.7–1.4), nothing like N=125's 5.99–9.36. That high figure is the "just bootstrapped, many
nodes churning" signature. It appears only on the day's *first* point and scales with N (more
concurrent chunker and indexer pods → more new `apps-compute` nodes → more image-pull bytes)
rather than with cluster freshness alone. N=10 ran on a fresh cluster and still shows none of it,
consistent with its low N needing few new nodes. N=10's *total* NAT ($2.61) is ~1.8x N=25's
($1.44), and that tracks its ~2.1x longer duration (2.207h against 1.029h) at a comparable or
lower hourly rate. The SQS-drain evidence in #10's Notes (709 → 639 over the 15 min around the
timeout) already showed ongoing work when the script gave up, so the manual recovery didn't
rescue a stall.

Taken together: N=10 is slow (0.76 docs/min, the lowest of any point, because only 3 TEI replicas
ever justified themselves at this concurrency), and every fixed per-hour cost (NAT, the
serving-pool floor, baseline compute) keeps accruing for as long as the run takes. The 2h12m wall
time is plausibly what a clean N=10 point costs rather than a corrupted read. With a single N=10
run, "plausibly" is as far as the data goes. A second, independent N=10 run (not attempted; the
cluster is gone) would turn this into a confirmed reading.

- **Knee** — N=50, the last point with a meaningful docs/min gain (25→50: +40%; 50→75: only
  +2.6%). Threshold used: 10% docs/min gain per step
- **Sweet spot** — N=25, the minimum `$/1M docs` ($24,875<!--FD75-->) among all five points, N=10 included.
  N=10's real cost ($44,707<!--FD76-->) is *higher*, and the NAT re-check shows that is a genuine reading of
  N=10's economics (low throughput keeps the fixed per-hour costs running longer), not a corrupted
  one. Landing on the lowest clean N swept is the case `methodology.md` §7 flags as unproven: the
  true minimum could sit below 25 (untested), or N=10 could already be past it and rising, which
  its real number now suggests
- **Waste boundary** — N=75, where `$/run` rises 35% for a 2.6% docs/min gain over N=50. It is the
  clearest case in this campaign of the cost curve decoupling from throughput
- **Gap cost** — $19,460<!--FD77--> extra per 1M docs paid running at the knee (N=50, $44,335<!--FD74-->) instead of
  the sweet spot (N=25, $24,875<!--FD75-->) → report §3.3
- **Reference value** — no pre-sweep default `maxReplicaCount` was frozen for this parameter. This is its first exploration, so there is nothing to compare against. Fargate equivalent (D29): not computed; the rate card exists and the pod-hours don't (§3 D29)
- **Condition boundary** — `00-baseline` §2 Envelope, plus packing density, bulk-drop arrival and the TEI trigger
- **Raw data** — no `./data/frontier.csv` was written and no `plot-frontier.py` exists. The Matrix is built directly from each point's `.jsonl`/`.cost-estimate.json`; chart it by hand from those files or from the Matrix before this execution closes

### M12 — split-cost decomposition by workload

Pulled 2026-09-09 from the same historical CUR parquet. The data was available all along;
`split_line_item_*` simply hadn't been read directly before. All five points' hour buckets are
still inside the export (ordinary CUR rows currently reach 2026-09-09; non-zero split rows stop at
2026-09-05T16:00Z, which covers every `01-ingestion` point with room to spare). Full detail →
`./data/m12-eks-split.json`.

**Scope caveat for the whole table** — this is the EKS split-cost-allocation slice only: each
pod's share of `AmazonEC2`/`AmazonEKS` instance vCPU+GB-hours, apportioned by resource request.
It leaves out NAT, gp3 volumes, the load balancer and every other non-instance-hour line, so these
rows do not sum to the Matrix's `$/run` and aren't meant to. `unused` is fleet-wide across EKS
(every node in the cluster, not just this project's pods): provisioned instance capacity that no
pod's request share claimed that hour.

| N | tei-embeddings | indexer | qdrant | api | chunker | **workload total** | unused (fleet-wide) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 10  | $0.4841 | $0.3405 | $0.3031 | $0.0317 | $0.0034 | **$1.1628** | $1.8478 |
| 25  | $0.3256 | $0.2574 | $0.2021 | $0.0217 | $0.0021 | **$0.8090** | $1.4787 |
| 50  | $0.2734 | $0.2660 | $0.1010 | $0.0108 | $0.0017 | **$0.6529** | $1.1984 |
| 75  | $0.3524 | $0.3018 | $0.1010 | $0.0116 | $0.0020 | **$0.7688** | $1.4556 |
| 125 | $0.4438 | $0.3971 | $0.1010 | $0.0109 | $0.0018 | **$0.9547** | $1.8123 |

The table agrees with the rest of this doc. `tei-embeddings` and `indexer` are always the two
real costs. The chunker's share stays near zero at every N, the same signature that put it
outside Tier 1 saturation: it is cheap and uncontended. `api` barely moves, matching "never
stressed" in Saturation. `qdrant`'s per-point share tracks wall time more than N, because both
replicas are always up regardless of load and a longer window buys more of their fixed cost
(n10's $0.30 against the flat ~$0.10 at n50/n75/n125).

**D26 — warm-up and unused capacity**: the `unused` column now gives real numbers. They are not
resolved into a formula, because `D26` was never defined beyond its name ("warm-up and unused
capacity") in this doc or `report.md`, the same gap `D30` has. The raw signal is there once a
definition is written: `unused` tracks wall time nearly 1:1, following `qdrant`'s pattern (both
are fleet idle-capacity effects), and not N.

**D27 — marginal decomposition**: partly answered by the M12 table, which splits the EKS
instance-hour slice per workload. It isn't the full decomposition the name implies, because NAT
and the other non-instance-hour lines, the majority of `$/run` at every N, are outside it
($0.9547 of EKS split cost against n125's $8.82<!--FD67--> `$/run`). Answered for compute, not for the run.

**D28 — amortization**: still declared not made. `M12` alone doesn't resolve it; it needs a
stated amortization horizon, which this doc never fixed.

**D29 — Fargate equivalent**: still declared not made. The rate is no longer missing:
`00-baseline`'s `./data/price-2026-09-09.json` has a real `eu-central-1` Fargate rate
($0.04656/vCPU-hour, $0.00511/GB-hour). The pod-hours are. `M12` gives dollars per workload
rather than raw CPU and memory pod-hours, and the Matrix's `N reached` column is the indexer's
time-weighted concurrency only. The chunker's concurrency (described as "headroom", never
measured as a time-weighted mean) appears nowhere in this doc. Computing D29 now would mean
guessing the chunker's average concurrency, so it isn't computed.

**Sizing check** — D30 against M18: not made. `D30` was never defined in `00-baseline` or
`report.md`, so there is nothing to compare `M18` against. `M18` was captured 2026-09-05, just
before cluster teardown, against the live 84,018-point collection (the same corpus and count as
every point): `qdrant-0` 379 MiB, `qdrant-1` 97.7 MiB, recorded in
`./data/m18-qdrant-working-set.json` for when `D30` is defined.

### Saturation

**Tier 1 — none, by resource signature. The constraint is architectural.**

- **Evidence** — neither `M6` (indexer and chunker CPU) nor TEI CPU reached its frozen limit at
  any point in the grid (checked live at several points during the campaign; Journal). The
  template's evidence field ("M6 at the frozen limit") has nothing to report, because nothing
  pegged. What held constant is the indexer's concurrency model: one in-flight TEI call per pod,
  fully sequential in `apps/indexer/src/main.py`, so replica count sets wall time directly and no
  component runs out of resources. `chunker` never exceeded a ~20-concurrent load with a mean
  around 1, regardless of N. That is a ceiling on corpus availability (8 consecutive points, N=10
  through 125), not on chunker capacity
- **Relieved by** — not applicable in the usual sense, since no ceiling exists that more
  resources would relieve. More `indexer` replicas already produced the whole observed throughput
  range: N reached tracked N set exactly at every point, with no sign of flattening by N=125

**Tier 2 — not attempted.** `M15`–`M17` (TEI queue depth, TEI inference duration, Qdrant
write/upsert latency) never got a working ServiceMonitor during the campaign. Declared, not
measured, as `report.md`'s Coverage table states.

No third tier is claimed. This section's template assumes a resource-pegged Tier 1 and has no
slot for what was found here (Retro, last line).

### Guardrails

- **`maxReplicaCount` = 20 ᴱ** — the sweet spot (N=25, $24,875<!--FD75-->/1M docs ᴰ) ran at a time-weighted
  mean of 19.5, so the cap bound only at the peak, and 20 is the concurrency the cheapest measured
  run actually sustained. Not a claim that 20 beats 25: no point separates them, and the grid's
  next step is 50. N=50 stays the knee, the documented ceiling for a hurry. Valid for this corpus
  only: the chunker's ~20-concurrent ceiling is corpus-driven (Saturation), so a larger corpus
  needs a re-check before this number transfers · live value raised 10 → 20 to match (2026-09-19,
  both ScaledJobs; never run at this value, the cluster is gone) ·
  `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml` → report §5
- **chunker `limits.memory`** — not revised. `00-baseline`'s `500m`/`1Gi` limits already carry a
  margin note (measured against a 78.8 MB sample; the corpus has untested files up to 124 MB), and
  nothing in this campaign changes that number, since the chunker was never the constraint at any N
- **indexer `limits.memory`** — not revised, for the same reason. The indexer's frozen `4Gi`
  limit already has a documented margin in `00-baseline`, and M8 (OOMKilled) was an
  instrumentation gap at every point rather than a confirmed zero, so ingestion data alone doesn't
  support raising or lowering it
- **`consolidateAfter`** — not revised. It already moved from `00-baseline`'s frozen `30s` to `5m`
  mid-campaign to fix a scheduling deadlock (postmortem, 2026-09-02). This campaign's D26, which
  would show whether the 5m tail costs material unused capacity, was never computed, so there is
  no basis to move it again

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — inverted. Tier 1 was expected to be the Stage-1 chunker (PyMuPDF, single-threaded). The chunker held headroom at every N (peak ~20 concurrent regardless of N ∈ [50,125]; its ceiling never bound). The actual constraint has no resource-ceiling signature: the indexer holds exactly one in-flight TEI call per pod (the fully sequential `for msg in messages: process_sqs_message(...)` in `apps/indexer/src/main.py`), so downstream concurrency is 1:1 with replica count. Neither indexer nor TEI CPU reached its frozen limit anywhere in the grid, yet `$/1M docs` rose monotonically (+22.5%, +12.7%, +11.6% per step). The ceiling is architectural, not a capacity limit
- **What should have been caught before the first run** — the plan's `§1 Expected` bet on a U-shaped cost curve. Nothing in `§1 Validity` would flag "no U-shape appears" as an anomaly, and correctly so: it is a valid finding the template didn't anticipate. Validity needs no fix; the gap is in the Saturation template (Back into the kit)
- **Concurrency delivered** — yes, cleanly: M5 (peak) matched N set exactly at all five points, N=10 through 125. The Spot pool never capped the top of the tested range. Headroom above N=125 was never tested (N=175 was dropped once the cost trend proved monotonic downward; Notes #08)
- **TEI response** — yes: TEI peak replicas scaled from 3 (N=10) to 26 (N=125), roughly linear in N, and its `D23` share of `$/run` grew with it (though `D23` is still the unresolved rough estimate, not confirmed by CUR)
- **Attribution** — good: `M9` and compute resolved to tagged CUR rows for all five points (N=10's CUR read landed 2026-09-07, after the others). Split cost allocation (`M12`) is pulled too (2026-09-09, §3). It answers "chunker vs. indexer vs. unused capacity" for the EKS instance-hour slice, on top of the "compute vs. serving vs. NAT" split from `resource_tags`. M12 was in the export the whole time; it just hadn't been queried before 2026-09-09
- **Month-close revision** — the 48h re-check is done (2026-09-07, Close checklist): unchanged
  for N=25/50/75/125, first real read for N=10. Still open: the *month*-close re-check. September
  hasn't closed, so a credit or true-up landing later this month wouldn't show in either CUR read
  so far
- **Back into the kit** — the Saturation template (§3) takes M6 at the frozen limit as its evidence field and has no slot for a constraint without a resource-ceiling signature, so this campaign had to put the finding in Retro prose. Add a second Saturation evidence type, "no component pegged, but the D-series unit-cost curve is monotonic across the swept range", so the next execution that hits this doesn't have to route around the template
