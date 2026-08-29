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

### Window

The window opens at the first `s3:ObjectCreated`, taken from the marker file the upload script
writes, and recorded by `run-point.py --start-marker`. Upload itself is outside the system under
test. The window closes when `apps-compute` reaches zero nodes, plus a five-minute buffer. It
does not close when the queues drain → K1.

### Metrics

The register is in `./metrics.md`. M1 through M6 are required: a point missing any of them has
no cost figure, no mechanism, or no Tier 1, and is not worth its cluster time. M7 and M8 through
M10 are optional. M7 missing degrades one line of D20 to estimated. M8 through M10 gate the
second constraint tier and nothing else, so the campaign starts without them rather than waiting.

The query file is `./scripts/queries.txt`, written with confirmed names only, dry run clean
⟨date⟩. Prometheus retention is ⟨3 d⟩, so export runs after every point. Extra points in an
export are harmless; a missing one costs a full re-run.

### Validity

A point is excluded when image digests, corpus or `00-baseline` §2 differ from the other points.
A point is excluded when the reset did not run and the collection was not recreated with
`--wipe-mode recreate`.

A point is not trusted when D14 and D15 disagree by more than a few percent. That means the run
stalled and recovered rather than draining steadily.

A point is re-run when R13 at close differs from the frozen corpus count. Documents were dropped
and the denominator lies.

A point is re-run when a node was lost during the window. It carries warm-up belonging to no
concurrency level. The alternative is to mark D18 estimated and exclude the point from the curve
fit. Averaging it in silently is not a third option.

### Safeguards

- **Estimated cost and duration** — 5 points × ⟨wall time⟩ · ⟨$⟩ ᴱ on Spot
- **Abort condition** — three consecutive points invalidated by node loss. The Spot pool cannot hold a run long enough to measure, which is a finding about resilience rather than something to push through

---

## 2 · Journal

One invocation per point. The script does preflight, window timing, interruption detection, the
R13 read, export, Qdrant reset, and emits the point block into `./data/`.

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
- [ ] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ.
- [ ] Outcome compared against Expected in Retro, inversion included.

---

## 3 · Results

**Finding** — ⟨one sentence: throughput plateaus at N=⟨⟩, unit cost bottoms at N=⟨⟩⟩ → report §3.3

### Matrix

| Run | N | Docs/min | Wall time | Node-h Spot | Node-h On-Dem | $/run | $/1M docs | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #01 | 4 | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #02 | 12 | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #03 | 24 | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #04 | ⟨⟩ | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #05 | ⟨⟩ | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |

- **Knee** — N=⟨⟩, the last point with a meaningful docs/min gain. Threshold used ⟨⟩
- **Sweet spot** — N=⟨⟩, the minimum `$/1M docs`. A minimum landing on the lowest or highest N swept is not proven (`methodology.md` §7)
- **Waste boundary** — N=⟨⟩, where `$/run` rises substantially for under 10 % throughput
- **Gap cost** — ⟨⟩ extra per 1M docs paid at the knee rather than at the sweet spot → report §3.3
- **Reference value** — ⟨the pre-sweep default N⟩, and the Fargate equivalent D22
- **Condition boundary** — `00-baseline` §2 Envelope, plus packing density and bulk-drop arrival
- **Raw data** — `./data/frontier.csv` · chart by `./scripts/plot-frontier.py` → `../../assets/`

**Warm-up share** — D19 at the lowest and highest N: ⟨⟩ → ⟨⟩ → report §3.4

**Marginal decomposition** — D20 at the sweet spot → report §4.2 · amortization D21 → §4.3 ·
Fargate equivalent D22 → §4.4

### Saturation

**Tier 1 — ⟨component⟩ at N=⟨⟩, run #⟨n⟩**

- **Evidence** — M5 at the frozen limit, with R12 recorded at the point
- **Relieved by** — more workers at higher N. Cost of the next step ⟨$⟩ ᴰ

**Tier 2 — ⟨claimed only if a new ceiling was observed after Tier 1 was actually relieved⟩**

- **Evidence** — M8, M9 or M10, if they landed
- **Relieved by** — ⟨not attempted⟩

No third tier is claimed (`methodology.md` §8). A point with R12 empty contributes its cost row
and nothing here.

### Guardrails

- **`maxReplicaCount` = ⟨n⟩** — from the sweet spot in Matrix · `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` → report §5
- **chunker `limits.memory` = ⟨⟩** — from M6 peak plus ⟨30⟩ % · `deploy/k8s/apps/chunker` → report §5
- **indexer `limits.memory` = ⟨⟩** — from M6 peak plus ⟨30⟩ % · `deploy/k8s/apps/indexer` → report §5
- **`consolidateAfter` = ⟨⟩** — from D19, only if the tail proves material · `apps-compute` NodePool → report §5

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — ⟨held · inverted — what actually saturated, in the words that go into the report⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught before the first run** — ⟨and which validity criterion should have caught it⟩
- **Spot basis** — ⟨did the frozen historical average match the actual run windows⟩
- **Back into the kit** — ⟨⟩
