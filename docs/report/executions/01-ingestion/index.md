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

- **Varied parameter** — KEDA `maxReplicaCount` (N) on ⟨indexer only · both stages⟩, in `deploy/k8s/apps/⟨…⟩/scaledjob.yaml`
- **Candidate grid** — N ∈ {4, 8, 12, 16, 20, 24}
- **Sweep order** — coarse to fine: {4, 12, 24}, then two refinement points placed by the shape those three produce (`methodology.md` §7). Five points total
- **Held constant** — image digests, corpus, TEI replicas, Qdrant collection config, instance type, and every row of `00-baseline` §2 Configuration freeze
- **Reset between points** — both queues at zero, `apps-compute` at zero nodes, collection recreated
- **Conditions carried to report §2** — bulk-drop arrival, and worker packing density of ≈ ⟨n⟩ per node → K2

The config commit moves between points and that is expected: the swept value lives in Git. What
must not move is the pair of image digests.

N is a ceiling, not a setting. What the axis actually delivers is M5, and the two are compared
at every point in §1 Validity.

### Window

The window opens at the first `s3:ObjectCreated`, taken from the marker file the upload script
writes, and recorded by `run-point.py --start-marker`. Upload itself is outside the system under
test. The window closes when `apps-compute` reaches zero nodes, plus a five-minute buffer. It
does not close when the queues drain → K1.

### Metrics

The register is in `./metrics.md`.

M1 through M8 are required. A point missing any of them has no cost figure, no mechanism, or no
Tier 1, and is not worth its cluster time.

M9 is required for the campaign and blocks no point. Its source is CloudWatch, which stays
readable for months, so it is collected once after the last point rather than per point. If it
never lands, one line of D22 is priced from the rate card and marked ᴱ.

M10 through M13 are optional. M10 through M12 gate the second constraint tier and nothing else.
M13 confirms one sizing number once, at the highest-N point. The campaign starts without them
rather than waiting for the ServiceMonitors.

The query file is `./scripts/queries.txt`, written with confirmed names only, dry run clean
⟨date⟩. M7 is exported at ⟨5 s⟩ while the rest of the file runs at ⟨15 s⟩. That is a partial
mitigation, not a fix: the sample rate is why M8 exists.

Selectors for M4, M6 and M7 cannot be confirmed on an idle cluster. Worker containers do not
exist at zero nodes, the query returns NO DATA, and that is indistinguishable from a missing
scrape target. Confirm them during a smoke run under load, not during preflight.

Prometheus retention is ⟨3 d⟩, so export runs after every point. Extra points in an export are
harmless; a missing one costs a full re-run.

### Validity

A point is excluded when image digests, corpus or `00-baseline` §2 differ from the other points.

A point is excluded when the reset did not run and the collection was not recreated with
`--wipe-mode recreate`.

A point is not trusted when M1 does not fall steadily: a plateau in the middle of the window
means the run stalled and recovered rather than draining, and the wall time behind D17 then
describes a stall rather than a concurrency level.

A point is labelled with M5 rather than with N when the two disagree. Spot capacity was short,
the point ran at what was granted, and filing it under the requested N puts a wrong x-value on
the frontier. Both numbers go in the matrix.

A point is re-run when R16 at close differs from the frozen corpus count. Documents were dropped
and the denominator lies.

A point is re-run when a node was lost during the window. It carries warm-up belonging to no
concurrency level. The alternative is to mark D20 estimated and exclude the point from the curve
fit. Averaging it in silently is not a third option.

A non-zero M8 does not invalidate the point's cost row. It invalidates the memory guardrail
derived from M7: a limit that produced an OOM is not a ceiling, and the replacement is raised
rather than fitted to the observed peak.

### Safeguards

- **Estimated cost and duration** — 5 points × ⟨wall time⟩ · ⟨$⟩ ᴱ on Spot
- **Abort condition** — three consecutive points invalidated by node loss. The Spot pool cannot hold a run long enough to measure, which is a finding about resilience rather than something to push through

---

## 2 · Journal

One invocation per point. The script does preflight, window timing, interruption detection, the
R16 read, export, Qdrant reset, and emits the point block into `./data/`.

```bash
../../scripts/run-point.py --run ingestion-n04 --n 4 --doc-count ⟨00-baseline §2⟩
```

Exit 0 means the point is clean. Paste the block, then read the saturation signal in Grafana
now, while the window is still in retention. Exit 1 means preflight failed and nothing ran.
Exit 2 means the export has gaps and nothing was wiped. Do not start the next point: the window
is still inside retention and can be re-exported. Exit 3 means interruptions were detected and
the point is suspect. Apply the node-loss rule in §1 Validity. Exit 4 means the run timed out
and nothing was exported. The point is lost.

### Run ledger

| # | Point | Window UTC | Commit | Outcome | Signal | Exported |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | ingestion-n04 | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨ok · aborted, ⟨reason⟩ · invalid, ⟨reason⟩⟩ | ⟨component at its ceiling · headroom⟩ ᴿ | ⟨✓ · —⟩ |
| 02 | ingestion-n12 | | | | | |
| 03 | ingestion-n24 | | | | | |
| 04 | ingestion-n⟨⟩ | | | | | |
| 05 | ingestion-n⟨⟩ | | | | | |

### Notes

**Decision after the coarse pass** — ⟨which two refinement points, and the shape that placed them⟩

**#⟨n⟩** — ⟨deviation from the plan, anomaly, mid-run decision, why it was aborted⟩

### Close

- [ ] Saturation identified, or headroom confirmed at the top of the grid.
- [ ] M9 read from CloudWatch for the whole campaign, or the D22 egress line marked ᴱ.
- [ ] M13 read at the highest-N point and compared against D25, or the comparison declared not made.
- [ ] Collection point count written back into `00-baseline` §2 Envelope.
- [ ] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ.
- [ ] Outcome compared against Expected in Retro, inversion included.

---

## 3 · Results

**Finding** — ⟨one sentence: throughput plateaus at N=⟨⟩, unit cost bottoms at N=⟨⟩⟩ → report §3.3

### Matrix

| Run | N set | N reached | Docs/min | Wall time | Node-h Spot | Node-h On-Dem | $/run | $/1M docs | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #01 | 4 | ⟨⟩ | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #02 | 12 | ⟨⟩ | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #03 | 24 | ⟨⟩ | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #04 | ⟨⟩ | ⟨⟩ | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #05 | ⟨⟩ | ⟨⟩ | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |

`N reached` is M5, time-weighted mean with the peak in brackets. The curve is fitted against it,
not against `N set`.

- **Knee** — N=⟨⟩, the last point with a meaningful docs/min gain. Threshold used ⟨⟩
- **Sweet spot** — N=⟨⟩, the minimum `$/1M docs`. A minimum landing on the lowest or highest N swept is not proven (`methodology.md` §7)
- **Waste boundary** — N=⟨⟩, where `$/run` rises substantially for under 10 % throughput
- **Gap cost** — ⟨⟩ extra per 1M docs paid at the knee rather than at the sweet spot → report §3.3
- **Reference value** — ⟨the pre-sweep default N⟩, and the Fargate equivalent D24
- **Condition boundary** — `00-baseline` §2 Envelope, plus packing density and bulk-drop arrival
- **Raw data** — `./data/frontier.csv` · chart by `./scripts/plot-frontier.py` → `../../assets/`

**Warm-up share** — D21 at the lowest and highest N: ⟨⟩ → ⟨⟩ → report §3.4

**Marginal decomposition** — D22 at the sweet spot → report §4.2 · amortization D23 → §4.3

**Fargate equivalent** — D24 → report §4.4. It prices this workload at Fargate rates and is a
lower bound on what Fargate would actually cost. Three mechanisms move it upward and none move
it down: no Spot capacity type exists for Fargate on EKS, so the comparison runs against
On-Demand rates; requests are billed at the next step of a fixed vCPU and memory grid; and each
task gets its own microVM, so image pull is paid per worker rather than amortised across a node.
The claim the report makes is therefore the conservative one.

**Sizing check** — D25 against M13: ⟨agree · disagree by ⟨⟩⟩. A disagreement is a `00-baseline`
revision, not a row here.

### Saturation

**Tier 1 — ⟨component⟩ at N=⟨⟩, run #⟨n⟩**

- **Evidence** — M6 at the frozen limit, with R15 recorded at the point
- **Relieved by** — more workers at higher N. Cost of the next step ⟨$⟩ ᴰ

**Tier 2 — ⟨claimed only if a new ceiling was observed after Tier 1 was actually relieved⟩**

- **Evidence** — M10, M11 or M12, if they landed
- **Relieved by** — ⟨not attempted⟩

No third tier is claimed (`methodology.md` §8). A point with R15 empty contributes its cost row
and nothing here.

### Guardrails

- **`maxReplicaCount` = ⟨n⟩** — from the sweet spot in Matrix · `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` → report §5
- **chunker `limits.memory` = ⟨⟩** — from M7 peak plus ⟨30⟩ %, valid only where M8 is zero · `deploy/k8s/apps/chunker` → report §5
- **indexer `limits.memory` = ⟨⟩** — from M7 peak plus ⟨30⟩ %, valid only where M8 is zero · `deploy/k8s/apps/indexer` → report §5
- **`consolidateAfter` = ⟨⟩** — from D21, only if the tail proves material · `apps-compute` NodePool → report §5

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — ⟨held · inverted — what actually saturated, in the words that go into the report⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught before the first run** — ⟨and which validity criterion should have caught it⟩
- **Spot basis** — ⟨did the frozen historical average match the actual run windows⟩
- **Concurrency delivered** — ⟨did M5 track N across the grid, or did the Spot pool cap the top⟩
- **Back into the kit** — ⟨⟩
