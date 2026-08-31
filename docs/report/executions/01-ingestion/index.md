# 01 · Ingestion concurrency

- **Why this execution exists** — how throughput and unit cost respond to ingestion concurrency on a Spot pool that scales to zero: how do we configure it?
- **Produces** — the efficiency frontier, the constraint ladder, and the marginal cost per document that report §4 cannot compute itself
- **Expected** — recorded ⟨date⟩, before the first run. Tier 1 is the Stage-1 chunker, not TEI. PyMuPDF extraction is single-threaded CPU work and may dominate embedding time by an order of magnitude, while the original design assumed inference would saturate first. Corollary: the unit-cost minimum sits below the throughput knee, driven by warm-up share rather than by any component ceiling
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Givens** — `00-baseline` §2, cited from there
- **Optional files** — `./metrics.md` register · `./concepts.md` mechanisms

---

## 1 · Plan

### Axis

- **Varied parameter** — KEDA `maxReplicaCount` (N), set to the same value on both ScaledJobs, in `deploy/k8s/apps/⟨…⟩/scaledjob.yaml`
- **Candidate grid** — N ∈ {4, 8, 12, 16, 20, 24}
- **Sweep order** — coarse to fine: {4, 12, 24}, then two refinement points placed by the shape those three produce (`methodology.md` §7). Five points total
- **Held constant** — image digests, corpus, Qdrant collection config, instance types, the TEI trigger, and every row of `00-baseline` §2 Configuration freeze
- **Not held constant, and measured instead** — TEI replicas. The indexer drives the same autoscaler the query path drives, so TEI scales during a run and its cost above the two-replica floor belongs to this execution → K5
- **Reset between points** — both queues at zero, `apps-compute` at zero nodes, TEI back at 2 replicas, collection recreated
- **Conditions carried to report §2** — bulk-drop arrival, worker packing density of ≈ ⟨n⟩ per node → K2, and the TEI trigger frozen in `00-baseline` §2

Here the potential is bounded by the queue, not by the client: the corpus is dropped in full
before the window opens, so work is always waiting and a higher ceiling is immediately consumed.
That is what makes a ceiling the right axis here and the wrong one in `02-inference`.

One N drives both stages. Fixing one stage while sweeping the other would make the fixed stage
the ceiling by construction, and the hypothesis above names a stage. The component split comes
from M6, whose selector already separates them.

The config commit moves between points and that is expected: the swept value lives in Git. What
must not move is the set of image digests.

N is a ceiling, not a setting. What the axis actually delivers is M5, and the two are compared
at every point in §1 Validity.

### Window

The window opens at the first `s3:ObjectCreated`, taken from the marker file the upload script
writes, and recorded by `run-point.py --start-marker`. Upload itself is outside the system under
test. The window closes when `apps-compute` reaches zero nodes **and** TEI has returned to two
replicas, plus a five-minute buffer. It does not close when the queues drain → K1.

**Points are scheduled one per clock hour.** Cost is read from hourly CUR buckets, and two
points sharing a bucket cannot be told apart inside it → K6. A point starts near the top of an
hour and the next one starts no earlier than the following hour.

No query load runs during this execution. TEI serves both paths and a concurrent query would
put its scale-out cost in two executions at once.

### Metrics

The register is in `./metrics.md`.

M1 through M9 are Prometheus-sourced and perishable. Retention is ⟨3 d⟩, so each of them gates
its point at the moment the point closes. A point missing any of them has no mechanism, no
Tier 1, or no denominator, and is not worth its cluster time.

M10 through M14 are CUR-sourced and cannot be read at point close: the export is delivered daily
and revised until the month ends → K6. They gate the campaign, not a point. The cost pass runs
once, at least 48 h after the last point, and fills the cost columns of every row in one go.

M15 through M18 are optional. M15 through M17 gate the second constraint tier and nothing else.
M18 confirms one sizing number once, at the highest-N point.

The Prometheus query file is `./scripts/queries.txt`, written with confirmed names only, dry run
clean ⟨date⟩. M7 is exported at ⟨5 s⟩ while the rest of the file runs at ⟨15 s⟩. That is a
partial mitigation, not a fix: the sample rate is why M8 exists → K3.

Selectors for M4, M6 and M7 cannot be confirmed on an idle cluster. Worker containers do not
exist at zero nodes, the query returns NO DATA, and that is indistinguishable from a missing
scrape target. Confirm them during a smoke run under load, not during preflight.

### Validity

A point is excluded when image digests, corpus or `00-baseline` §2 differ from the other points.

A point is excluded when the reset did not run: the collection was not recreated with
`--wipe-mode recreate`, or TEI had not returned to two replicas before the window opened. A run
that starts with TEI already warm carries capacity it did not pay for.

A point is excluded when its window shares an hourly CUR bucket with another point. The compute
cost of the two cannot be separated after the fact, and both lose their cost row → K6.

A point is not trusted when M1 does not fall steadily: a plateau in the middle of the window
means the run stalled and recovered rather than draining, and the wall time behind D22 then
describes a stall rather than a concurrency level.

A point is labelled with M5 rather than with N when the two disagree. Spot capacity was short,
the point ran at what was granted, and filing it under the requested N puts a wrong x-value on
the frontier. Both numbers go in the matrix.

A point is re-run when R21 at close differs from the frozen corpus count. Documents were dropped
and the denominator lies.

A point is re-run when a node was lost during the window. It carries warm-up belonging to no
concurrency level. The alternative is to mark the point estimated and exclude it from the curve
fit. Averaging it in silently is not a third option.

A point loses its M12 decomposition, but keeps its cost row, when split cost allocation returns
no rows for its pods. The total is billed either way; only the per-component share depends on
the feature → K5.

A non-zero M8 does not invalidate the point's cost row. It invalidates the memory guardrail
derived from M7: a limit that produced an OOM is not a ceiling, and the replacement is raised
rather than fitted to the observed peak → K3.

### Safeguards

- **Estimated cost and duration** — 5 points × ⟨wall time⟩ · ⟨$⟩ ᴱ on Spot, spread over ⟨n⟩ hours by the one-point-per-hour rule
- **Abort condition** — three consecutive points invalidated by node loss. The Spot pool cannot hold a run long enough to measure, which is a finding about resilience rather than something to push through

---

## 2 · Journal

One invocation per point. The script does preflight, window timing, interruption detection, the
R21 read, Prometheus export, TEI and Qdrant reset, and emits the point block into `./data/`. It
does not read cost.

```bash
../../scripts/run-point.py --run ingestion-n04 --n 4 --doc-count ⟨00-baseline §2⟩
```

Exit 0 means the point is clean. Paste the block, then read the saturation signal in Grafana
now, while the window is still in retention. Exit 1 means preflight failed and nothing ran.
Exit 2 means the export has gaps and nothing was wiped. Do not start the next point: the window
is still inside retention and can be re-exported. Exit 3 means interruptions were detected and
the point is suspect. Apply the node-loss rule in §1 Validity. Exit 4 means the run timed out
and nothing was exported. The point is lost.

The cost pass is a second script, run once for the whole campaign:

```bash
../../scripts/cur-window.py --execution 01-ingestion --after 48h
```

It reads every window from the point blocks, sums M10 through M14 over the matching hourly
buckets, subtracts the serving pool idle rate from `00-baseline` §2, and writes the cost columns
back into `./data/frontier.csv`.

### Run ledger

| # | Point | Window UTC | Commit | Outcome | Signal | Exported | Cost read |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | ingestion-n04 | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨ok · aborted, ⟨reason⟩ · invalid, ⟨reason⟩⟩ | ⟨component at its ceiling · headroom⟩ ᴿ | ⟨✓ · —⟩ | ⟨✓ · —⟩ |
| 02 | ingestion-n12 | | | | | | |
| 03 | ingestion-n24 | | | | | | |
| 04 | ingestion-n⟨⟩ | | | | | | |
| 05 | ingestion-n⟨⟩ | | | | | | |

`Exported` is filled when the run ends. `Cost read` is filled by the cost pass, days later, and
a blank there after the pass ran is a lost cost row rather than a lost point.

### Notes

**Decision after the coarse pass** — ⟨which two refinement points, and the shape that placed them⟩

**#⟨n⟩** — ⟨deviation from the plan, anomaly, mid-run decision, why it was aborted⟩

### Close

- [ ] Saturation identified, or headroom confirmed at the top of the grid.
- [ ] Cost pass run at least 48 h after the last point, and re-run after the month closed if any figure moved.
- [ ] M12 decomposition present, or the per-component split declared not made.
- [ ] TEI peak replicas recorded at every point, and D23 computed or declared zero.
- [ ] M18 read at the highest-N point and compared against D30, or the comparison declared not made.
- [ ] Collection point count written back into `00-baseline` §2 Envelope.
- [ ] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ.
- [ ] Outcome compared against Expected in Retro, inversion included.

---

## 3 · Results

**Finding** — ⟨one sentence: throughput plateaus at N=⟨⟩, unit cost bottoms at N=⟨⟩⟩ → report §3.3

### Matrix

| Run | N set | N reached | TEI peak | Docs/min | Wall time | Compute $ | TEI $ | Other $ | $/run | $/1M docs | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #01 | 4 | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #02 | 12 | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #03 | 24 | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #04 | ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #05 | ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |

`N reached` is M5, time-weighted mean with the peak in brackets. The curve is fitted against it,
not against `N set`. `TEI peak` is M9. `Compute $` is M10 and is billed rather than computed.
`TEI $` is D23, already net of the two-replica floor. `Other $` is M13 plus M14.

- **Knee** — N=⟨⟩, the last point with a meaningful docs/min gain. Threshold used ⟨⟩
- **Sweet spot** — N=⟨⟩, the minimum `$/1M docs`. A minimum landing on the lowest or highest N swept is not proven (`methodology.md` §7)
- **Waste boundary** — N=⟨⟩, where `$/run` rises substantially for under 10 % throughput
- **Gap cost** — ⟨⟩ extra per 1M docs paid at the knee rather than at the sweet spot → report §3.3
- **Reference value** — ⟨the pre-sweep default N⟩, and the Fargate equivalent D29
- **Condition boundary** — `00-baseline` §2 Envelope, plus packing density, bulk-drop arrival and the TEI trigger
- **Raw data** — `./data/frontier.csv` · chart by `./scripts/plot-frontier.py` → `../../assets/`

**Warm-up and unused capacity** — D26 at the lowest and highest N: ⟨⟩ → ⟨⟩ → report §3.4

**Marginal decomposition** — D27 at the sweet spot → report §4.2 · amortization D28 → §4.3

**Fargate equivalent** — D29 → report §4.4. It prices the worker pods at Fargate rates and is a
lower bound on what Fargate would actually cost. Three mechanisms move it upward and none move
it down: no Spot capacity type exists for Fargate on EKS, so the comparison runs against
On-Demand rates; requests are billed at the next step of a fixed vCPU and memory grid; and each
task gets its own microVM, so image pull is paid per worker rather than amortised across a node.
TEI is outside the comparison — it is a shared deployment on the serving pool either way.

**Sizing check** — D30 against M18: ⟨same order · differ by ⟨⟩⟩. A disagreement in magnitude is
a `00-baseline` revision, not a row here → K4.

### Saturation

**Tier 1 — ⟨component⟩ at N=⟨⟩, run #⟨n⟩**

- **Evidence** — M6 at the frozen limit, with R20 recorded at the point
- **Relieved by** — more workers at higher N. Cost of the next step ⟨$⟩ ᴰ

**Tier 2 — ⟨claimed only if a new ceiling was observed after Tier 1 was actually relieved⟩**

- **Evidence** — M15, M16 or M17, if they landed. A TEI ceiling here is a scaler ceiling rather than a hardware one, and M9 says which
- **Relieved by** — ⟨not attempted⟩

No third tier is claimed (`methodology.md` §8). A point with R20 empty contributes its cost row
and nothing here.

### Guardrails

- **`maxReplicaCount` = ⟨n⟩** — from the sweet spot in Matrix · `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` → report §5
- **chunker `limits.memory` = ⟨⟩** — from M7 peak plus ⟨30⟩ %, valid only where M8 is zero · `deploy/k8s/apps/chunker` → report §5
- **indexer `limits.memory` = ⟨⟩** — from M7 peak plus ⟨30⟩ %, valid only where M8 is zero · `deploy/k8s/apps/indexer` → report §5
- **`consolidateAfter` = ⟨⟩** — from D26, only if the unused-capacity share proves material · `apps-compute` NodePool → report §5

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — ⟨held · inverted — what actually saturated, in the words that go into the report⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught before the first run** — ⟨and which validity criterion should have caught it⟩
- **Concurrency delivered** — ⟨did M5 track N across the grid, or did the Spot pool cap the top⟩
- **TEI response** — ⟨did TEI scale at all under ingestion, and did its share of `$/run` grow with N⟩
- **Attribution** — ⟨did every point resolve to tagged CUR rows, and did split cost allocation return pods on every point⟩
- **Month-close revision** — ⟨did any cost figure move between the 48 h read and the closed month⟩
- **Back into the kit** — ⟨⟩
