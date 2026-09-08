# 01 · Ingestion concurrency

- **Why this execution exists** — how throughput and unit cost respond to ingestion concurrency on a Spot pool that scales to zero: how do we configure it?
- **Produces** — the efficiency frontier, the constraint ladder, and the marginal cost per document that report §4 cannot compute itself
- **Expected** — recorded ⟨date⟩, before the first run. Tier 1 is the Stage-1 chunker, not TEI. PyMuPDF extraction is single-threaded CPU work and may dominate embedding time by an order of magnitude, while the original design assumed inference would saturate first. Corollary: the unit-cost minimum sits below the throughput knee, driven by warm-up share rather than by any component ceiling
- **Status** — running
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Givens** — `00-baseline` §2, cited from there

---

## 1 · Plan

### Axis

- **Varied parameter** — KEDA `maxReplicaCount` (N), one value on both ScaledJobs, in `deploy/k8s/apps/⟨…⟩/scaledjob.yaml`. Fixing one stage while sweeping the other makes the fixed stage the ceiling by construction, and the hypothesis names a stage. The split between them comes from M6 → K7
- **Candidate grid** — N ∈ {4, 24, 50, 100, 125, 175}, revised from the original {4,8,12,16,20,24} — `ingestion-n50-test` (§2 Journal) showed indexer still at its full N=50 ceiling with no plateau (M5: 50/50 concurrent, vs. chunker's 20/50), meaning the original top of 24 would never have found indexer's real knee. Ceiling raised to 175 against the new Spot quota (192, up from 96) with headroom left for TEI
- **Sweep order** — coarse to fine: {4, 50, 175}, then refinement points placed by the shape those three produce (`methodology.md` §7). `ingestion-n50-test` already covers the N=50 point
- **Held constant** — image digests, corpus (`zabiullah/pdf-books-collection`, **stratified 100-file / 1.38 GB sample**, drawn from the full 1,041-PDF / 14.52 GB set — see Notes), Qdrant collection config, instance types, the TEI trigger, and every row of `00-baseline` §2 Configuration freeze. The config commit moves between points: the swept value lives in Git
- **Not held constant, and measured instead** — TEI replicas. The indexer drives the same autoscaler the query path drives, so TEI scales during a run and its cost above the two-replica floor belongs to this execution → K5
- **Reset between points** — both queues at zero, `apps-compute` at zero nodes, TEI back at 2 replicas, collection recreated
- **Conditions carried to report §2** — bulk-drop arrival, worker packing density of ≈ ⟨n⟩ per node → K2, and the TEI trigger frozen in `00-baseline` §2

### Window

- **Opens** — first `s3:ObjectCreated`, from the marker the upload script writes · recorded by `run-ingestion-point.py --start-marker`. Upload is outside the system under test
- **Closes** — `apps-compute` at zero nodes **and** TEI back at 2 replicas, plus ⟨5⟩ min. Not at queue drain → K1
- **Spacing** — one point per clock hour → K6
- **Excluded from the window** — query load. TEI is shared, and its scale-out would be priced in two executions at once → K5

### Metrics

The register is in `./metrics.md`. PromQL for M1–M9 is in `./data/series.txt` and `./data/guards.txt`, confirmed names only, dry run clean ⟨date⟩.

### Validity

| Condition | Action | Ref |
| :--- | :--- | :--- |
| image digests, corpus or `00-baseline` §2 differ from the other points | exclude | |
| reset did not run — collection not recreated, or TEI above 2 at open | exclude | K5 |
| the window shares an hourly CUR bucket with another point | exclude | K6 |
| M1 does not fall steadily | not trusted — the wall time behind D22 describes a stall | |
| M5 disagrees with N | file the point under M5, both numbers in the matrix | K7 |
| a node was lost during the window | re-run, or mark ᴱ and drop it from the curve fit | K1 |
| R21 differs from the frozen corpus count | re-run — the denominator lies | |
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

Before `watch`, launches the corpus upload itself and uses that launch instant as the window
start — no marker file. After export, runs `prepare-cluster-for-ingestion.py` (S3 clean → SQS
purge → kill chunker/indexer Jobs → reset Qdrant → wait for `apps-compute` at zero and TEI at
floor) to leave the cluster ready for the *next* point, not this one — a fresh point still opens
on whatever the previous point's reset left behind, and the very first point needs the cluster
reset by hand first (below).

| Flag | Effect |
| :--- | :--- |
| `--no-prepare` | skip the cluster reset after export — reset by hand, or rely on organic drain |
| `--prepare-timeout <s>` | override the reset's wait-for-floor timeout (default 900s) |
| `--no-upload` | upload out of band — falls back to `--start`/`--start-marker`, else an inferred, poll-granularity start |
| `--upload-dir` / `--upload-prefix` | a different corpus than the default sample |

`prepare-cluster-for-ingestion.py` also runs stand-alone — run it once before the first point:

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
| 01 | ingestion-n04      | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨ok · aborted, ⟨reason⟩ · invalid, ⟨reason⟩⟩ | ⟨component at its ceiling · headroom⟩ ᴿ | ⟨✓ · —⟩ | ⟨✓ · —⟩ |
| 02 | ingestion-n24      | | | | | | |
| 03 | ingestion-n50-test | 2026-09-01T12:51:46Z → 13:43:14Z | `cacb7f5` (dirty) | ok — see Notes for the two node-loss warnings, reclassified benign | indexer at ceiling, M5 50/50 concurrent · chunker headroom, 20/50 ᴿ | ✓ (recovered by hand, `export-metrics.py --force`) | — |
| 04a | ingestion-n100-sticky | 2026-09-03T15:19:31Z → 15:57:48Z | `9c280655cea7` | superseded — sticky TEI routing, see Notes; re-run after fix | indexer at N ceiling (M5 100/100) but M6=0.146, not CPU-bound ᴱ | ✓ (8/9, M8 gap) | — |
| 04 | ingestion-n100     | 2026-09-03T16:24:23Z → 17:05:31Z | `cfa0ab7` (dirty) | ok — post-fix, see Notes for the wall-clock/cost nuance | indexer at N ceiling, M5 100/100 · chunker headroom 20/100 · TEI peak ~23 replicas ᴿ | ✓ (8/9, M8 gap — same GC-race as n100-sticky) | — |
| 05 | ingestion-n125     | 2026-09-04T14:00:58Z → 14:39:25Z | `15d43d5` (dirty) | ok — closed by hand after the runner process was killed externally, see Notes | indexer at N ceiling, M5 125/125 · chunker headroom 20/125 · TEI peak 26 replicas ᴿ | ✓ (8/9, M8 gap) | ✓ CUR, see Notes under #08 |
| 06 | ingestion-n75      | 2026-09-04T15:06:08Z → 15:48:59Z | `1b5ad91` (dirty) | ok — off-plan refinement point, see Notes | indexer at N ceiling, M5 75/75 · chunker headroom 20/75 · TEI peak 16 replicas ᴿ | ✓ (8/9, M8 gap) | ✓ CUR, see Notes under #08 |
| 07 | ingestion-n50      | 2026-09-04T16:01:22Z → 16:45:23Z | `005914d` (dirty) | ok — post-fix, fresh cluster instance (see Notes) | indexer at N ceiling, M5 50/50 · chunker headroom 20/50 | ✓ (8/9, M8 gap) | ✓ CUR, see Notes under #08 |
| 08 | ingestion-n25      | 2026-09-04T17:00:55Z → 18:02:39Z | `1d87721` (dirty) | ok — see Notes for the NAT methodology bug found here | indexer at N ceiling, M5 25/25 · chunker headroom 20/25 · TEI peak 4 replicas | ✓ (8/9, M8 gap) | ✓ CUR, see Notes under #08 |
| 09 | ingestion-n175     | not run — top of the original grid, dropped once the trend proved monotonic downward through n25 | | | | | |
| 10 | ingestion-n10      | 2026-09-05T10:27:09Z → 12:39:36Z | `4e15a2c` (dirty) | non-standard — new cluster, corpus reloaded to repopulate Qdrant for `02-inference`; script itself timed out (exit 4, 1h30m max wait), closed by hand after manual polling confirmed convergence + buffer, see Notes | indexer at N ceiling, M5 10/10 · **chunker also at N ceiling, 10/10** (first point where N < chunker's own ~20 corpus cap) · TEI peak 3 replicas | ✓ (8/9, M8 gap) | ᴰ, floor only — 5/11 nodes unpriced (see Notes) |

`Exported` is filled when the run ends. `Cost read` is filled by the cost pass, days later, and
a blank there after the pass ran is a lost cost row rather than a lost point.

### Notes

**Corpus provisioning** — 1,041 PDFs (14.52 GB) uploaded to the raw-docs bucket in 387 s
(37.6 MB/s) via `download-pdf-books-dataset.py` + `upload-dir-to-s3.py` (16 workers, 16 MB
multipart threshold). Throughput matched the operator's home uplink, not S3 or the
scripts' concurrency — the HF download side independently ran at a comparable ~34 MB/s. Not
a system-under-test figure, and excluded from every point's window (§1 Window: upload is
outside the system under test).

**Corpus resized to a stratified sample** — full corpus made a five-point sweep with resets
impractical. 100-file / 1.38 GB sample (~9.5%), stratified over 10 size deciles at seed 42 so
the size-mix driving PyMuPDF time matches the full corpus (13.77 MB/file mean vs. 13.96 MB).
Manifest: `../../../../tmp/ingest-sample-manifest.tsv` · files: `tmp/ingest-sample/` (untracked).

**Decision after the coarse pass** — ⟨which two refinement points, and the shape that placed them⟩

**#03 ingestion-n50-test** — run off-plan (N=50 wasn't in the original grid) to validate the
automation end-to-end before the real sweep; kept as a real grid point after the fact since it
came back clean. Two things looked like they'd invalidate it and didn't:

- *Two "node left" warnings* (`ip-10-0-11-186`, `ip-10-0-12-180`, both at 13:10:14Z, logged
  while combined queue depth was 1427). Investigated against M4: neither node ever had a single
  chunker/indexer container scheduled to it in the whole window — Karpenter's
  `WhenEmpty`/`WhenEmptyOrUnderutilized` consolidation only ever disrupts an already-empty node,
  so these were ordinary teardown of nodes that happened to be idle while other nodes still had
  backlog, not lost work. `run-ingestion-point.py`'s detection was checking system-wide queue
  depth rather than that specific node's own workload — fixed (`labkit.pods_by_node` +
  `FORCED_REASONS`, `SpotInterrupted`/`TerminatingOnInterruption`/`InstanceStopping` only) so
  future points don't get flagged on this by mistake.
- *Export gap* — both local port-forwards (Prometheus, Qdrant) died around minute 27 of the
  51m28s window (`labkit.PortForwards` had no health-check). `run-ingestion-point.py` correctly
  refused to wipe on the export failure; recovered by hand with the exact command it printed,
  8/9 refs came back clean (M8/OOMKilled empty is a real zero, nothing OOM'd). Also fixed
  (`PortForwards.ensure_alive()`, called from the watch loop and before R21/export).

R21 confirmed 84,018 points from the 100-file sample post-recovery.

**#04a ingestion-n100-sticky** — TEI load badly imbalanced across replicas mid-run (`te_queue_size` in
the hundreds on some pods, zero on others simultaneously), despite the headless-Service fix
from the prior session (§1 of that postmortem). Root cause is not the Service — confirmed in
code, not inferred: `huggingface_hub.utils._http.get_session()` returns a process-wide
singleton `httpx.Client` (`apps/indexer/.venv/.../huggingface_hub/utils/_http.py:335`,
"shared between all calls"), and `apps/indexer/src/main.py` builds the Haystack pipeline once
per pod and reuses it across the pod's whole `while not graceful_exit` SQS-poll loop — so one
indexer pod's entire embedding traffic rides a single TCP connection for its lifetime, pinned
to whichever TEI backend Cilium's L4 hash picked on first connect. TEI replicas that scale out
mid-run get no traffic until a fresh connection happens to land on them.

**Ceiling check, from the exported data (M5/M6):** indexer M5 = 100/100 (hit the concurrency
ceiling, matches N set) but M6 = 0.146 — only 14.6% of its CPU budget (workers × window ×
limit). Far from CPU-bound while sitting at its full concurrency ceiling is exactly the
signature of pods blocked waiting on a slow dependency rather than computing — consistent with
the sticky-TEI-routing finding above (6 of 19 TEI replicas carrying hundreds of queued
requests while 13 sat idle). chunker M5 = 20/100, M6 = 0.012 — unaffected, same headroom as
`n50-test`.

**Decision: this run does not stand as a grid point.** The concurrency ceiling is real (M5
matches N), but throughput at that ceiling is suppressed by the routing artifact, not by the
system being measured — `$/run` and `docs/min` here are pessimistic relative to what N=100
looks like once TEI load is actually spread across replicas. Renamed to `ingestion-n100-sticky`
(ledger #04a) so the id `ingestion-n100` was free for a clean re-run. This run's data (window
`2026-09-03T15:19:31Z → 15:57:48Z`, commit `9c280655cea7`) is kept here as the documented cause,
not averaged in. Provisional cost estimate (karpenter/EC2/CloudWatch reconstruction, not CUR):
`./data/ingestion-n100-sticky.cost-estimate.json`, `D24 ≈ $1.85/run` — inflated for the same
reason (nodes stayed up longer waiting on TEI, not computing).

Fix deployed (`32365dc`, `apps/indexer/src/main.py`) — `argocd-image-updater` stopped
considering the `indexer` alias for updates partway through this session for an undiagnosed
reason (survived a clean pod restart, so not a cache/backoff issue); resolved by hand via
`deploy/k8s/apps/indexer/.argocd-source-indexer.yaml` pointing straight at the built digest,
same workaround `postmortem.md` §11 used before. `ingestion-n100` re-run under the fixed image.

**M8 gap, same run** — export also came back with `M8` (OOMKilled) empty
(`export-metrics.py` exit 2, correctly not a silent zero). Root cause: by the time export ran,
all 6 retained Job objects (`successfulJobsHistoryLimit`/`failedJobsHistoryLimit` = 3+3) had
zero pods left — `kube_pod_container_status_last_terminated_reason` lives on the Pod object,
and orphaned-pod GC removes it once its node is gone, regardless of the Job's own history limit.
`apps-compute`'s `consolidateAfter` (5m, not the `00-baseline`-frozen 30s — same divergence
flagged there) meant nodes started tearing down well before export ran. Exported anyway via
`export-metrics.py --force` (writes the file despite the gap; `--force` only means "overwrite",
not "ignore the gap") — 8/9 refs are good, M8 is a documented instrumentation gap for this run,
not a claimed zero. Worth revisiting before a point where an OOM signal actually matters. Same
gap recurred on `#04 ingestion-n100` below (same GC race, not a new bug) — also `--force`d.

Two more instrumentation bugs found and fixed while chasing this: `run-ingestion-point.py`'s
and `prepare-cluster-for-ingestion.py`'s Qdrant checks both treated `HTTP 404` (collection
doesn't exist — the correct state right after a delete-based reset) the same as "unreachable",
failing preflight on a perfectly clean cluster. Both now treat 404 as `points == 0`.

**#04 ingestion-n100** — real point, post-fix (`32365dc`, deployed by hand via
`.argocd-source-indexer.yaml` after `argocd-image-updater` stopped picking up the `indexer`
alias — undiagnosed, survived a clean pod restart). R21 = 84,018, same as the sticky run
(same corpus). `te_queue_size`/per-pod CPU confirmed live during the run: settled TEI replicas
no longer sit at zero for their whole life the way they did pre-fix — a brand-new pod ramps
from ~0.5 to ~2.4 cores within about a minute of joining, instead of staying pinned near zero
indefinitely.

**But the aggregate numbers are not a clean win** — flagging honestly rather than declaring
victory:

| | `n100-sticky` | `n100` (fixed) | Δ |
| :--- | :--- | :--- | :--- |
| Window | 2298 s (38m17s) | 2468 s (41m08s) | **+7.4%**, longer |
| `M10` compute $ | $1.3808 | $1.2877 | **−6.7%**, cheaper |
| `M11` serving gross $ | $0.5684 | $0.8698 | **+53.0%**, much more |
| TEI peak replicas | ~19 | ~23 | higher |

Compute cost did drop — consistent with indexer pods spending less time blocked waiting on TEI.
But total wall-clock went up, not down, and TEI scaled to more replicas (peaked ~23 vs ~19) —
plausibly because fixing the routing let indexer drive genuine concurrent demand across TEI
backends instead of a few being saturated while most sat idle, so *aggregate* demand on TEI (and
its own scale-out) rose rather than fell. The fix demonstrably solved the fairness/attribution
problem — confirmed live, not just inferred from an aggregate — but it did not obviously reduce
this run's total `$/run` or wall-clock time. Left as an open question for Retro rather than
resolved here; provisional estimate with the full breakdown at
`./data/ingestion-n100.cost-estimate.json` (`D24 ≈ $1.76/run`, vs. the sticky run's `$1.85` —
close enough that the "fix helps cost" claim is not proven either way from one pair of runs).

**#05 ingestion-n125** — started deliberately at the `14:00:00Z` hour boundary (K6: keep this
point's window inside its own UTC clock hour). Cluster was reset and re-frozen ahead of time
(new cluster instance post-teardown — see `tmp/post-mortem/postmortem-2026-09-03-...md` §11 —
`argocd-image-updater` was not involved this time, `root-bootstrap`/`rag-apps` synced cleanly
straight to the branch tip on first bootstrap). `maxReplicaCount` raised to 125 on both
`chunker`/`indexer` ScaledJobs.

Queue drained cleanly, `apps-compute` reached zero, TEI back at floor — the runner
(`run-ingestion-point.py`) was already holding the close buffer (`nodes=0, tei=2` since
`14:34:25Z`, needs 300s) when its background process was killed externally (not a script
crash — the harness reported a `killed` status, most likely a session interrupt). Verified the
cluster had not drifted since (R21 already 84,018, `apps-compute` still at 0) before treating
`14:39:25Z` as the close time and running `export-metrics.py --force` /
`prepare-cluster-for-ingestion.py` by hand — same data the script would have produced on its
own, just assembled manually.

R21 confirmed 84,018 — same corpus, same count, third run in a row. M5: indexer 125/125 (full
ceiling, tracks N exactly, same signature as `n50-test` and `n100`), chunker 20/125 (same
demand ceiling as every prior run — this is now four points confirming chunker's cap is
corpus-driven, not `maxReplicaCount`-driven). TEI peaked at **26** replicas, up from `n100`'s 23
— consistent with the linear-ish scaling predicted from the indexer architecture analysis (not
yet CPU-bound, not yet at TEI's own ceiling of 30).

Cost estimate (karpenter/EC2/CloudWatch, same method as `n100`):
`./data/ingestion-n125.cost-estimate.json` — `M10` compute $1.44 (up from `n100`'s $1.29),
`M11` serving gross $0.98 (up from $0.87), `D24 ≈ $1.97/run`. Both cost lines moved up together
with N this time (unlike the `n100-sticky → n100` comparison, where compute and serving moved
in opposite directions) — a cleaner, more expected shape. Still only one measurement per N,
same statistical caveat as before applies.

**Live incident during prep** — the `argocd.argoproj.io/compare-options: ServerSideDiff=true`
fix from the previous session (meant to stop qdrant's self-heal loop, see
`tmp/post-mortem/postmortem-2026-09-03-...md` §4) turned out to panic this cluster's
`gitops-engine` (v0.7.1) on at least some apps — confirmed in
`argocd-application-controller` logs: `Recovered from panic: invalid memory address or nil
pointer dereference` in `diff.removeWebhookMutation`. The panic is caught per-app, but that
app's reconcile that cycle silently aborts — this is what was actually blocking
`indexer`/`chunker` from picking up new commits, not `argocd-image-updater` (which was the
suspect in the `n125` prep). Reverted the annotation in git, but ArgoCD ApplicationSet only
*adds/updates* annotations from its template — it does not prune ones removed from the
template, so the revert alone didn't clear it from the 9 already-generated Applications; had
to `kubectl patch --type merge` each one directly (`{"metadata":{"annotations":{"...
compare-options":null}}}`) to actually remove it. Confirmed clean afterward (0 panics/minute).
The qdrant self-heal loop this was meant to fix is left unfixed — cosmetic, no pod disruption,
not worth risking this again without testing against this cluster's actual ArgoCD version first.

**#06 ingestion-n75** — off-plan, added after `n125`: with `n100`/`n125` both showing indexer
comfortably below its CPU ceiling (M6 ~12-17%) and TEI below its own replica ceiling (23/30,
26/30), the shape between 50 and 100 was still unknown — `n50-test` and `n100` bracket a wide
gap. Ran at N=75 to fill it in before committing to `n175`.

R21 = 84,018 — fifth point in a row with the identical count. M5: indexer 75/75 (full ceiling,
same signature as every other point), chunker 20/75 — **fifth consecutive confirmation** that
chunker's ceiling is corpus-driven (fixed at 20 regardless of `maxReplicaCount`), not a
`maxReplicaCount` artifact. TEI peaked at 16, continuing the roughly-linear relationship with N
(16 → 23 → 26 for N = 75 → 100 → 125).

**First look at the cost trend, three points (75/100/125)** — `$/1M docs` rose **monotonically**
with N ($15,623 → $17,613 → $19,657), the opposite of the U-shaped curve §1 Expected predicted.
Superseded two points later by the four-point table below (same numbers, plus n50) — not
repeated here. Still single-run-per-N at this stage, same caveat as the `n100-sticky → n100`
comparison, but three points already agreeing on a direction was the first sign this might hold.

**#07 ingestion-n50** — fresh point (not reusing `n50-test`, see Notes above #06) to complete the
trend below `n75`. R21 = 84,018, sixth point in a row with the identical count. M5: indexer
50/50 (full ceiling), chunker 20/50 — sixth consecutive confirmation of the corpus-driven
chunker cap. Also noted live: two `tei-embeddings` pods sat `Terminating` for 5–12 min mid-run
— traced to `apps-serving`'s `consolidationPolicy: WhenEmptyOrUnderutilized` evicting pods to
repack nodes as TEI scaled down (`Evicted pod: Underutilized` in pod events), pod object then
stuck until orphaned-pod GC caught up with the node's own teardown — same underlying mechanism
as the `M8` gap, different symptom. Not data-losing (SQS redelivers), just added noise/latency
late in the window.

**Cost trend, four points now — the monotonic pattern holds down to N=50:**

| N | `M10` compute | `M11` serving gross | `D24` $/run | `D25` $/1M docs |
| :--- | :--- | :--- | :--- | :--- |
| 50  | $0.98 | $0.50 | $1.28 | $12,750 |
| 75  | $1.19 | $0.69 | $1.56 | $15,623 |
| 100 | $1.29 | $0.87 | $1.76 | $17,613 |
| 125 | $1.44 | $0.98 | $1.97 | $19,657 |

Four points, one direction, no reversal — the U-shape `§1 Expected` predicted has not shown up
anywhere in the range tested (50–125). Either the minimum sits below 50 (untested — the
original grid's next-lowest point is `N=24`), or there isn't a U-shape in this range at all and
lower N is simply cheaper per document throughout, at the cost of wall-clock time. Still
single-run-per-N (no repeated trials, no error bars) — but four points agreeing is a much
stronger signal than the two-point comparisons earlier in this doc. Worth a real `docs/min` /
`N reached` pull across all four before writing the Finding in §3 — this section only tracked
$-figures, not throughput, so "cheaper" here has not yet been checked against "how much slower."

**#08 ingestion-n25** — extends the trend one point lower. R21 = 84,018 again, seventh point in
a row with the identical count. M5: indexer 25/25 (full ceiling), chunker 20/25 — seventh
consecutive confirmation of the corpus-driven chunker cap. TEI peaked at 4 replicas (M9), and the
burst was absorbed by the same 2 `apps-serving` nodes that were already up at the floor for the
whole window — no extra serving node was billed, so `D23` is correctly $0 here, not an omission.

**NAT methodology bug found here, retroactive to every prior point** — `M14` for n50/n75/n100/n125
was computed from `AWS/NATGateway`'s `BytesInFromSource` metric alone (the outbound leg: pods'
requests leaving through NAT). AWS bills NAT data processing on *both* legs of a flow, and the
inbound leg (`BytesInFromDestination` — responses coming back through NAT) was never queried.
For an ingestion point, that inbound leg is dominated by `chunker`/`indexer` container image
pulls from `ghcr.io` (external registry, not ECR — no VPC endpoint, so every pull is billed NAT
traffic) each time Karpenter boots a fresh `apps-compute` node. Confirmed directly on n25's own
window: a 5-minute-resolution CloudWatch profile shows >99% of the window's `BytesInFromDestination`
landing in the first 10 minutes (17:00–17:10Z), exactly the node-bootstrap window recorded by
`karpenter-cost-estimate.py`'s own node list (first `apps-compute` nodes seen 17:02:55–17:04:55Z).
Background trickle after that: ~0.01–0.03 GB / 5 min.

Recomputed both directions from raw CloudWatch bytes:

| Run | old `M14` (outbound leg only) | corrected `M14` (both legs) | ratio |
| :--- | :--- | :--- | :--- |
| n50 | $0.0163 | $2.6080 | ×160 |
| n25 | $0.0109 (would have been, same old method) | $1.1989 | ×110 |

n25's ledger and `./data/ingestion-n25.cost-estimate.json` use the corrected figure: `D24` =
$0.875 (`M10`) + $0 (`D23`) + $0 (`M13`) + $1.199 (`M14`) = **$2.074/run, $20,739/1M docs** —
already higher than every prior point's *reported* $/1M docs despite N=25 being the lowest N run
so far, which is itself informative: at low N the image-pull NAT tax is a larger share of a
smaller total run cost, so it may flatten or invert part of the monotonic trend above once
corrected consistently.

A same-day spot-check on n50 alone (CloudWatch bytes, before CUR was available) already moved its
`D24` from $1.275 to $3.867/run — over 3× the reported figure, and the direction that made pulling
real CUR numbers for all four points worth doing immediately rather than waiting. Result below.

**CUR actuals pulled (2026-09-05, 00-baseline §2's source of record) — the estimates above are
now superseded, not just for `M14`.** CUR delivered a batch covering all of `2026-09-04` (all
four points fall in it). Queried `s3://simple-rag-cur-reports-883f615c` directly, grouped by
`line_item_usage_start_date`'s hour (each point occupies a distinct UTC hour, by design — K6) and
by `resource_tags['user_karpenter_sh_nodepool']` for compute/serving, and by the NAT gateway's own
`line_item_resource_id` (`arn:...natgateway/nat-08e283a51761f1e9b`) for NAT — which turned out to
bill under product code `AmazonEC2`, not `AmazonVPC` as assumed, and to carry a further line item
(`EUC1-DataTransfer-Regional-Bytes`) never priced in either the original or the corrected
CloudWatch-based `M14` above.

| N | reported `D24` | CUR compute | CUR NAT (both legs + regional transfer) | CUR marginal (compute+NAT+SQS+S3) | ratio | real `D25` $/1M docs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 125 | $1.97  | $2.0069 | $5.9919 | **$8.00** | ×4.1 | $79,999 |
| 75  | $1.56  | $1.5446 | $4.0939 | **$5.64** | ×3.6 | $56,396 |
| 50  | $1.275 | $1.2613 | $2.8776 | **$4.14** | ×3.2 | $41,400 |
| 25  | $0.886 | $1.0916 | $1.3823 | **$2.48** | ×2.8 | $24,750 |

`CUR marginal` = tagged `apps-compute` cost + the NAT gateway's full line-item set for that hour +
SQS + S3 (both ~$0 — free-tier-covered at this volume) — deliberately excludes `apps-serving`
(shown gross alongside compute in the underlying query, $1.20/$0.90/$0.68/$0.39 for
125/75/50/25 — TEI-above-floor `D23` net-of-floor still isn't resolved from CUR, same open item
as before) and excludes ~$0.9–1.15/hour of `baseline_other` (EKS control plane, two core nodes —
`r7g.large`, `t3.large` — ELB, CloudWatch, KMS) present in every hour regardless of N, which is
fixed cluster overhead, not marginal to any one point.

Two things confirmed, one thing newly found:
- **Direction holds** — the monotonic rise with N is real, not a `M14`-methodology artifact.
- **Magnitude was badly understated** — even after yesterday's NAT-bug fix (§ above), real
  `D24`/`D25` are 2.8×–4.1× the reported figures, growing *with* N (the gap is worst at the top
  of the tested range, not uniform) — meaning the reported figures underweighted exactly the
  scenario (high N, many nodes) where the real cost is furthest from the estimate.
- **Compute was also off**, independent of NAT — `describe-spot-price-history`-at-node-start-time
  (`karpenter-cost-estimate.py`'s method) reads 15–25% below what CUR actually billed for the same
  instances. Spot price can move between the price snapshot and the actual charged rate; this
  estimator was never meant to replace CUR (says so in its own docstring), and this is the
  concrete gap that statement was hedging against.

Re-pulled 2026-09-07, past the 48h guard: unchanged for all four points — no credits or true-ups
moved anything. The table above is final.

**#10 ingestion-n10** — off-plan, run on a freshly-bootstrapped cluster (2026-09-05) for a
different reason than any prior point: `02-inference`'s precondition needs a loaded Qdrant
collection, no snapshot/restore mechanism exists yet (`00-baseline`'s "restored from the
01-ingestion snapshot" was aspirational — never actually built; see `vector-db-historic` fix
below), and the cluster's own Qdrant was empty. Reloading the same 100-file corpus doubles as a
real, off-plan grid point below n25, so it's recorded here rather than thrown away.

`run-ingestion-point.py` itself timed out (exit 4 — "did not converge", nothing exported or wiped
by the script) at its default 1h30m max wait; the queue was still draining, not stuck (SQS
stage-2 depth fell from 709 to 639 over the 15 minutes surrounding the timeout). Watched by hand
past that point — converged at `12:34:36Z`, held the 300s buffer clean, then exported and priced
manually. Total window ended up **2h12m**, more than 4× any prior point's wall time, at less than
half n25's N — the clearest wall-clock evidence yet that low N trades real time for cost, not
just theoretically.

M5: chunker 10/10, indexer 10/10 — **first point where chunker doesn't show headroom**. Every
prior point (25 through 125) had chunker capped at ~20 regardless of `maxReplicaCount`, read as a
corpus-driven ceiling. Here N=10 sits below that ceiling, so chunker fills to N instead — evidence
*for* the corpus-cap reading, not against it: chunker's own appetite is still ≥10 here, it was
`maxReplicaCount` binding this time, not the corpus.

Same-day provisional estimate was a floor, not a real figure: 5 of 11 nodes seen in the window
resolved to `instance_type: "?"` in `karpenter-cost-estimate.py` (short-lived, replaced early,
past EC2's ~1h post-termination `describe-instances` visibility by the time pricing ran). `apps-serving`
also churned through 5 distinct node IDs against a floor of 2, so `D23` was left unresolved.
Superseded 2026-09-07 by a real CUR read: **$41,624/1M docs** — see the Matrix in §3 for the
number and why it breaks the otherwise-clean N-vs-cost trend. `./data/ingestion-n10.cost-estimate.json`
has the provisional breakdown, `./data/ingestion-n10.cur-actual.json` the real one.

**Fix landed alongside this point**: `02-inference`'s Qdrant-restore precondition had no actual
implementation (checked — no snapshot/restore script existed anywhere in the repo). Took a live
snapshot of this point's resulting collection via Qdrant's own REST API
(`POST /collections/simple-rag/snapshots`) and uploaded it to a new bucket,
`s3://vector-db-historic/qdrant-384-1gb-snapshot` (496 MB, 84,018 points) — the first snapshot
this project has ever actually taken, as opposed to the CronJob in
`deploy/k8s/platform/qdrant/qdrant-backup-cronjob.yaml` that assumes one exists. Restore is still
manual (download + Qdrant's snapshot-recovery API), not scripted — noted, not blocking.

### Close

- [ ] Saturation identified, or headroom confirmed at the top of the grid.
- [x] Cost pass run at least 48 h after the last point (2026-09-07) — unchanged for N=25/50/75/125, first real read for N=10. Re-run after the month closes still open.
- [ ] M12 decomposition present, or the per-component split declared not made.
- [ ] TEI peak replicas recorded at every point, and D23 computed or declared zero.
- [x] `M14` re-pulled with both `AWS/NATGateway` byte-direction legs, then superseded entirely by real CUR actuals (2026-09-05) — see Notes under #08.
- [ ] CUR-based `D23` (TEI above floor, net) — the CUR pull above reports `apps-serving` gross per hour but doesn't yet net out the two-replica floor rate; same open item as the CloudWatch-based estimate, not yet solved by switching to CUR.
- [x] Re-checked the CUR pull after 48h (2026-09-07) — N=25/50/75/125 unchanged from the ~24h read, no credits/true-ups moved anything.
- [ ] M18 read at the highest-N point and compared against D30, or the comparison declared not made.
- [ ] Collection point count written back into `00-baseline` §2 Envelope.
- [ ] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ.
- [ ] Outcome compared against Expected in Retro, inversion included.

---

## 3 · Results

**Finding** — Throughput never plateaus in the tested range (N=10–125): docs/min rises
monotonically with N throughout (0.76 → 2.60), so no saturation point exists to name as a knee in
the throughput sense the plan expected. Unit cost also never bottoms in the middle of the range —
`$/1M docs` rises monotonically with N as well, so the cheapest tested point is the lowest valid
one (N=25). The U-shaped cost curve `§1 Expected` predicted did not appear; more concurrency
bought real throughput at every step, just at a worse and worse cost-per-document exchange rate
→ report §3.3

### Matrix

`N reached` below is M5's time-weighted mean over the whole window (queue drain and buffer tails
pull it well below peak), peak in brackets. Cost columns for N=25/50/75/125 are CUR actuals,
**re-pulled 2026-09-07 (>48h after the last point) and unchanged from the original 2026-09-05
read** — the 48h-guard flag is now cleared, no revision, no credits/true-ups moved anything.
N=10's CUR actual was pulled for the first time on 2026-09-07 (no CUR window covered it before —
it ran a day after the other four, see `./data/ingestion-n10.cur-actual.json`). `TEI $` (D23) is
still the pre-CUR rough estimate for N=25–125 — CUR-based net D23 was never resolved (Close
checklist) — marked ᴰ throughout, not ᴿ; not available at all for N=10.

| Run | N set | N reached | TEI peak | Docs/min | Wall time | Compute $ | TEI $ | Other $ | $/run | $/1M docs | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #10 | 10 | 9.0 (10) | 3 | 0.76 | 132.5 min | $1.55 | — ᴱ (not resolved) | $2.61 | $4.16 ᴿ (D23 excluded) | **$41,624** | chunker *also* at N ceiling — the one point below the corpus's own ~20-concurrent cap |
| #08 | 25 | 19.5 (25) | 4 | 1.62 | 61.7 min | $1.09 | $0.00 ᴰ | $1.38 | $2.48 | $24,750 | none — indexer at ceiling, no resource pegged |
| #07 | 50 | 32.6 (50) | 10 | 2.27 | 44.0 min | $1.26 | $0.28 ᴰ | $2.88 | $4.42 | $44,200 | none |
| #06 | 75 | 40.5 (75) | 16 | 2.33 | 42.9 min | $1.54 | $0.35 ᴰ | $4.10 | $5.99 | $59,896 | none — the "waste boundary": +35% cost for +2.6% docs/min over N=50 |
| #05 | 125 | 63.5 (125) | 26 | 2.60 | 38.5 min | $2.01 | $0.50 ᴰ | $5.99 | $8.50 | $84,999 | none |

N=10 (#10) is still flagged non-standard for a different reason now: it has a real CUR cost, but
it's the outlier that breaks the otherwise-clean monotonic N-vs-cost trend — $41,624 sits right
next to N=50's $44,200, not below N=25's $24,750 the way the throughput trend alone would
predict. Most likely explanation: the script's own timeout and the ~2h12m manual-recovery wall
time (4× any other point) inflated NAT/baseline exposure over far more clock-hours than a clean
N=10 run would need — this reads as "N=10 run inefficiently," not "N=10 is fundamentally not
cheap." A clean re-run of N=10 (not attempted — cluster is gone) would be needed to settle which.

- **Knee** — N=50, the last point with a meaningful docs/min gain (25→50: +40%; 50→75: only
  +2.6%). Threshold used: 10% docs/min gain per step
- **Sweet spot** — N=25, the minimum `$/1M docs` ($24,750) among the four points with a clean
  cost read. N=10's real cost ($41,624) doesn't unseat it, but doesn't confirm it either — see the
  non-standard-run caveat above; a genuinely clean point below N=25 is still untested. Landing on the
  lowest N swept (excluding the non-standard N=10) is exactly the case `methodology.md` §7 flags
  as unproven — the true minimum may sit below 25, untested
- **Waste boundary** — N=75, where `$/run` rises 35% for a 2.6% docs/min gain over N=50 — the
  single clearest example of the cost curve decoupling from throughput in this campaign
- **Gap cost** — $19,450 extra per 1M docs paid running at the knee (N=50, $44,200) instead of
  the sweet spot (N=25, $24,750) → report §3.3
- **Reference value** — no pre-sweep default `maxReplicaCount` was ever frozen for this parameter — this is the first exploration of it, so there is nothing to compare against here. Fargate equivalent (D29): not computed, see below
- **Condition boundary** — `00-baseline` §2 Envelope, plus packing density, bulk-drop arrival and the TEI trigger
- **Raw data** — no `./data/frontier.csv` was written and no `plot-frontier.py` exists — the Matrix above is built directly from each point's `.jsonl`/`.cost-estimate.json`; chart by hand from those, or from the table above, before this execution closes

**Warm-up and unused capacity** — D26 declared not made. It needs `M12` (CUR split-cost
allocation, `split_line_item_unused_cost`), which was never pulled — the CUR reads this campaign
used grouped by `resource_tags`, not by the split-cost-allocation columns proper. The closest
proxy actually collected is `N reached` vs `N set` in the Matrix above (indexer ran at a
time-weighted mean of 50–65% of its peak across every point) — a real signal that a large share
of every window is ramp/drain, not steady throughput, but not the same measurement D26 asks for.

**Marginal decomposition** — D27 and amortization D28 both declared not made, same reason as
D26 (both are `M12` splits).

**Fargate equivalent** — D29 declared not made. Its formula needs pod-hours "behind M12" — same
blocker. A rough substitute (frozen worker resource requests × wall time, ignoring the
per-task-microVM and cold-start effects the definition itself says only push the real number
higher) was not attempted rather than published as if it were the real thing.

**Sizing check** — D30 against M18: not made. `D30` itself was never defined anywhere in
`00-baseline` or `report.md` — nothing exists to compare `M18` against. `M18` itself was captured
2026-09-05, just before cluster teardown, against the live 84,018-point collection (same corpus/
count as every point): `qdrant-0` 379 MiB, `qdrant-1` 97.7 MiB — recorded in
`./data/m18-qdrant-working-set.json` for whenever `D30` gets defined.

### Saturation

**Tier 1 — none, by resource signature. The real constraint is architectural.**

- **Evidence** — Neither `M6` (indexer/chunker CPU) nor TEI CPU reached its frozen limit at any
  point in the grid (confirmed live at multiple points during the campaign — see Journal). The
  saturation template's own evidence field ("M6 at the frozen limit") has no value to report:
  nothing pegged. What *did* hold constant is indexer's own concurrency model — one in-flight
  TEI call per pod, fully sequential per `apps/indexer/src/main.py` — so wall time is
  set by replica count directly, not by any component running out of resource. `chunker` never
  exceeded a ~20-concurrent, mean-1-ish load regardless of N — a corpus-availability ceiling
  (confirmed 8 consecutive points, N=10 through 125), not a chunker capacity ceiling
- **Relieved by** — not applicable in the usual sense: there is no ceiling to relieve by adding
  resource. More `indexer` replicas is what already produced the entire observed throughput
  range: N reached tracked N set exactly at every point, with no sign of flattening by N=125

**Tier 2 — not attempted.** `M15`–`M17` (TEI queue depth, TEI inference duration, Qdrant
write/upsert latency) never landed a working ServiceMonitor for the whole campaign — declared,
not measured, same as `report.md`'s own Coverage table already states.

No third tier is claimed. This section's own template assumed a resource-pegged Tier 1 and had
no slot for what was actually found here — see Retro's last line.

### Guardrails

- **`maxReplicaCount` = 50** — from the sweet-spot-adjacent knee in Matrix (N=25 is cheapest but
  untested below; N=50 is the last point with real throughput gain and is the more defensible
  operating point pending a lower-N point) · `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml` → report §5
- **chunker `limits.memory`** — not revised. `00-baseline`'s existing `500m`/`1Gi` limits already
  carry their own margin note (measured against a 78.8 MB sample; corpus has files up to 124 MB
  untested) — nothing in this campaign's data changes that number, since chunker was never the
  constraint at any N
- **indexer `limits.memory`** — not revised, same reasoning: indexer's own frozen `4Gi` limit
  already has margin documented in `00-baseline`, and M8 (OOMKilled) was an instrumentation gap
  at every point, never a confirmed zero, so raising or lowering this from ingestion data alone
  isn't supported
- **`consolidateAfter`** — not revised. Already diverged from `00-baseline`'s frozen `30s` to
  `5m` mid-session to fix a real scheduling deadlock (postmortem, 2026-09-02) — this campaign's
  D26 (which would show whether that 5m tail is now costing material unused capacity) was never
  computed, so there's no basis here to move it again

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — inverted. Expected Tier 1 to be the Stage-1 chunker (PyMuPDF, single-threaded). Chunker held headroom at every N (peak ~20 concurrent regardless of N ∈ [50,125], its own ceiling never binding). The actual constraint has no resource-ceiling signature at all: indexer holds exactly one in-flight TEI call per pod (`apps/indexer/src/main.py` — fully sequential `for msg in messages: process_sqs_message(...)`), so downstream concurrency is 1:1 with replica count. Neither indexer nor TEI CPU ever reached its frozen limit across the grid, yet `$/1M docs` rose monotonically (+22.5%, +12.7%, +11.6% per step) — an architectural ceiling, not a capacity one
- **What should have been caught before the first run** — the plan's own `§1 Expected` bet on a U-shaped cost curve; nothing in `§1 Validity` would have caught "no U-shape appears" as an anomaly, because it isn't one — it's a real, valid finding the template just didn't anticipate. Nothing to fix in Validity; the gap is in Saturation's template shape, noted below
- **Concurrency delivered** — yes, cleanly: M5 (peak) matched N set exactly at all five points, N=10 through 125. The Spot pool never capped the top of the tested range — headroom for N>125 was never exhausted, it was simply never tested (N=175 dropped from the plan once the cost trend proved monotonic downward, see Notes #08)
- **TEI response** — yes: TEI peak replicas scaled from 3 (N=10) to 26 (N=125), a roughly linear response to N, and its `D23` share of `$/run` grew with it in the same direction (though `D23` itself is still the unresolved rough estimate, not CUR-confirmed)
- **Attribution** — mostly: `M9`/compute resolved to tagged CUR rows for four of five points (N=25/50/75/125 — N=10 fell outside the CUR window pulled). Split cost allocation (`M12`) was never actually used — this campaign's CUR reads used `resource_tags` grouping instead, which answers "compute vs. serving vs. NAT" but not "chunker vs. indexer vs. unused capacity" — a real, acknowledged gap, not a silent one
- **Month-close revision** — not yet checked. The CUR pull behind the Matrix above is ~24h old at time of writing, not the 48h the Close checklist asks for, and the month hasn't closed. Flagged in the Matrix header; re-check needed before these figures are treated as final
- **Back into the kit** — the Saturation template (§3) asks for M6-at-frozen-limit as the evidence field; it has no slot for a constraint with no resource-ceiling signature. This campaign needed to write the real finding in Retro prose instead of in Saturation because the template assumed the wrong shape. Add a second Saturation evidence type — "no component pegged, but the D-series unit-cost curve is monotonic across the swept range" — so the next execution that hits this doesn't have to route around the template
