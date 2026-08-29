# 01 · Ingestion concurrency

- **Why this execution exists** — how throughput and unit cost respond to ingestion concurrency on a Spot pool that scales to zero: *how do we configure it?*
- **Produces** — the efficiency frontier, the constraint ladder, and the marginal cost per document that report §4 cannot compute itself
- **Expected** — recorded ⟨date⟩, before the first run: **Tier 1 is the Stage-1 chunker, not TEI.** PyMuPDF extraction is single-threaded CPU work and may dominate embedding time by an order of magnitude, while the original design assumed inference would saturate first. Corollary: the unit-cost minimum sits below the throughput knee, driven by warm-up share rather than by any component ceiling
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Givens** — `00-baseline` §2, cited from there. Mechanisms: `00-baseline/K5` · `K7` · `K8`

---

## 1 · Plan

### Axis

- **Varied parameter** — KEDA `maxReplicaCount` (N) on ⟨indexer only · both stages⟩, `deploy/k8s/apps/⟨…⟩/scaledjob.yaml`
- **Candidate grid** — N ∈ {4, 8, 12, 16, 20, 24}
- **Sweep order** — coarse to fine: {4, 12, 24}, then two refinement points placed by the shape those three produce (`methodology.md` §7). Five points total
- **Held constant** — image digests · corpus · TEI replicas · Qdrant collection config · instance type · every row of `00-baseline` §2 Configuration freeze
- **Reset between points** — both queues at zero, `apps-compute` at zero nodes, collection recreated
- **Conditions carried to report §2** — bulk-drop arrival · worker packing density ≈ ⟨n⟩ per node → `00-baseline/K8`

The config commit moves between points and that is expected: the swept value lives in Git.
What must not move is the pair of image digests.

### Window

- **Opens** — first `s3:ObjectCreated`, from the marker file written by the upload script · recorded by `run-point.py --start-marker`. Upload is outside the system under test
- **Closes** — `apps-compute` at zero nodes plus a 5-minute buffer — **not** queue drain → `00-baseline/K7` · recorded by `run-point.py`

### Metrics

Register in `./metrics.md`. Required: M1–M6. Optional: M7 · M8 · M9 · M10 → `00-baseline/K5`.

### Validity

| Criterion | What happens when it fails |
| :--- | :--- |
| Image digests, corpus and `00-baseline` §2 identical across points | point excluded |
| Reset performed, collection recreated (`--wipe-mode recreate`) | point excluded |
| D14 and D15 agree within a few percent | the run stalled and recovered rather than draining steadily — point not trusted |
| R13 at close equals the frozen corpus count | documents were dropped and the denominator lies — re-run |
| No node lost during the window | the point carries warm-up belonging to no concurrency level — re-run, or mark `D18` estimated and exclude it from the curve fit. Averaging it in silently is not a third option |

### Safeguards

- **Estimated cost / duration** — 5 points × ⟨wall time⟩ · ⟨$⟩ ᴱ on Spot
- **Abort condition** — three consecutive points invalidated by node loss: the Spot pool cannot hold a run long enough to measure, which is a finding about resilience rather than something to push through

---

## 2 · Journal

One invocation per point. The script does preflight, window timing, interruption detection,
`R13`, export, Qdrant reset, and emits the point block into `./data/`.

```bash
../../scripts/run-point.py --run ingestion-n04 --n 4 --doc-count ⟨00-baseline §2⟩
```

| Exit | Meaning | Next action |
| :--- | :--- | :--- |
| 0 | clean | paste the block, then read R12 in Grafana **now** |
| 1 | preflight failed | nothing ran |
| 2 | export gaps, **nothing wiped** | do not start the next point — the window is still inside retention |
| 3 | interruptions, point suspect | apply the node-loss rule in §1 Validity |
| 4 | timeout, nothing exported | point lost |

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
- [ ] Every figure in §3 marked (unmarked · ᴰ · ᴿ · ᴱ).
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

- **Knee** — N=⟨⟩, last point with a meaningful docs/min gain · threshold used ⟨⟩
- **Sweet spot** — N=⟨⟩, minimum `$/1M docs`. A minimum landing on the lowest or highest N swept sits on a range boundary and is **not proven** (`methodology.md` §7)
- **Waste boundary** — N=⟨⟩, `$/run` up substantially for under 10 % throughput
- **Gap cost** — ⟨⟩ extra per 1M docs paid at the knee rather than at the sweet spot → report §3.3
- **Reference value** — ⟨the pre-sweep default N⟩ · Fargate equivalent `D22`
- **Condition boundary** — `00-baseline` §2 Envelope, plus packing density and bulk-drop arrival
- **Raw data** — `./data/frontier.csv` · chart by `./scripts/plot-frontier.py` → `../../assets/`

**Warm-up share** — `D19` at the lowest and highest N: ⟨⟩ → ⟨⟩ → report §3.4

**Marginal decomposition** — `D20` at the sweet spot → report §4.2 · amortization `D21` → §4.3 · Fargate equivalent `D22` → §4.4

### Saturation

**Tier 1 — ⟨component⟩ at N=⟨⟩, run #⟨n⟩**

- **Evidence** — M5 at the frozen limit, R12 recorded at the point
- **Relieved by** — more workers at higher N; cost of the next step ⟨$⟩ ᴰ

**Tier 2 — ⟨claimed only if observed after Tier 1 was actually relieved⟩**

- **Evidence** — M8 · M9 · M10, if they landed
- **Relieved by** — ⟨not attempted⟩

No third tier is claimed (`methodology.md` §8). A point with R12 empty contributes its cost
row and nothing here.

### Guardrails

- **`maxReplicaCount` = ⟨n⟩** — from the sweet spot in Matrix · `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` → report §5
- **chunker `limits.memory` = ⟨⟩** — from M6 peak + ⟨30⟩ % · `deploy/k8s/apps/chunker` → report §5
- **indexer `limits.memory` = ⟨⟩** — from M6 peak + ⟨30⟩ % · `deploy/k8s/apps/indexer` → report §5
- **`consolidateAfter` = ⟨⟩** — from `D19`, only if the tail proves material · `apps-compute` NodePool → report §5

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — ⟨held · **inverted** — what actually saturated, in the words that go into the report⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught before the first run** — ⟨and which validity criterion should have caught it⟩
- **Spot basis** — ⟨did the frozen historical average match the actual run windows⟩
- **Back into the kit** — ⟨⟩
