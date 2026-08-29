# 01 · Ingestion concurrency

| Field | Value |
| :--- | :--- |
| Why this execution exists | how throughput and unit cost respond to ingestion concurrency on a Spot pool that scales to zero — *how do we configure it?* |
| Produces | the efficiency frontier, the constraint ladder, and the marginal cost per document that report §4 cannot compute itself |
| Expected *(recorded ⟨date⟩, before the first point)* | **Tier 1 is the Stage-1 chunker, not TEI** — PyMuPDF extraction is single-threaded CPU work and may dominate embedding time by an order of magnitude. The original design assumed inference saturates first. Corollary: the unit-cost minimum sits below the throughput knee, driven by warm-up share rather than by any component ceiling |
| Status | ⟨planned · running · closed · abandoned⟩ |
| Plan frozen | ⟨date⟩ · commit ⟨sha⟩ |
| Inherits | `00-baseline` — Constants · Metrics register · Applicability |
| Data · Scripts | `./data/` one `⟨point⟩.point.md` + one export per point · `./scripts/queries.txt` · driver `../../scripts/run-point.py` |
| Optional files | `./concepts.md` · `./metrics.md` — none |

> §1 is frozen before the first point and is not edited afterwards. If it turns out wrong,
> say so in Retro — `methodology.md` §7.

---

# 1 · Plan  *(frozen ⟨date⟩)*

## Axis

| Field | Value |
| :--- | :--- |
| Varied | KEDA `maxReplicaCount` (N) on ⟨indexer only · both stages⟩ → M3 |
| Candidate grid | N ∈ {4, 8, 12, 16, 20, 24} |
| Order | coarse to fine — {4, 12, 24}, then two refinement points chosen by the shape those three produce. Five points total (`methodology.md` §8) |
| Held constant | image digests · corpus · TEI replicas · Qdrant config · instance type · every row of `00-baseline` Constants |

The config commit moves between points and that is expected — the swept value lives in Git.
What must not move is the pair of image digests.

## Conditions added on top of baseline Applicability

| Condition | True only during | Mechanism |
| :--- | :--- | :--- |
| Bulk-drop arrival — the whole corpus uploaded at once, not a stream | every point | — |
| Reset between points: both queues at zero, `apps-compute` at zero nodes, collection wiped | every point | — |
| Worker packing density ≈ ⟨n⟩ per node | every point | → M2, and it belongs in the report Envelope |
| N applies to ⟨which ScaledJob⟩ | every point | → M3 |

## Window rule

| Boundary | Signal | Recorded by |
| :--- | :--- | :--- |
| Opens | first `s3:ObjectCreated` — marker file written by the upload script | `run-point.py --start-marker` |
| Closes | `apps-compute` at **zero nodes**, plus a 5-minute buffer — not queue drain → M1 | `run-point.py` |

## What this run reads

Names live in `00-baseline/metrics.md` — referenced, never redefined.

| Ref | Read as | Selector | Gates | Required |
| :--- | :--- | :--- | :--- | :--- |
| E1 | queue depth; its derivative is the drain rate | per queue, never summed | drain-rate cross-check · saturation candidate | yes |
| E2 | billable nodes over the window, by capacity type | `label_karpenter_sh_nodepool="apps-compute"` | node-hours → every $ figure | yes |
| E3 · E4 | node created → first pod ready | node selector as E2 · pods owned by the ScaledJobs | warm-up share → report §3.4 | yes |
| E10 | worker CPU as a fraction of the frozen limit | `namespace` + per-component `container` | **Tier 1 proof** | yes |
| E11 | worker peak working set | as E10 | two guardrail rows | yes |
| E5 | egress bytes, NAT-bound | ⟨`00-baseline` Open⟩ | the NAT line of the marginal decomposition | no |
| E20 · E21 · E30 | TEI queue, TEI duration, Qdrant write latency | job selector | report §3.5 Tier 2 — one claim → `00-baseline` M5 | no |

| Field | Value |
| :--- | :--- |
| Read once per point, not scraped | Qdrant `points_count` at window close, over REST, by `run-point.py` |
| Recorded by hand | the saturation signal — which component was at its ceiling, and from which metric → M5 |
| Query file | `./scripts/queries.txt` · dry run clean ⟨date⟩ |
| Export | after every point. Retention is ⟨3 d⟩; a missing point costs a full re-run |

## Validity criteria

| Criterion | What happens when it fails |
| :--- | :--- |
| Identical across points: image digests, corpus, `00-baseline` Constants | point excluded |
| Reset between points, collection recreated (`--wipe-mode recreate`) | point excluded |
| Docs/min agrees within a few percent between wall clock and the drain-rate derivative | the run stalled and recovered rather than draining steadily — point not trusted |
| `points_count` at close equals the corpus document count | documents were dropped and the denominator lies — re-run |
| No node lost during the window | the point carries warm-up belonging to no concurrency level — re-run, or mark `$/1M docs` estimated and exclude from the curve fit. Averaging it in silently is not a third option |

## Cost and stop condition

| Field | Value |
| :--- | :--- |
| Estimated | 5 points × ⟨wall time⟩ · ⟨$⟩ estimated, Spot |
| Stop if | three consecutive points are invalidated by node loss — the Spot pool cannot hold a run long enough to measure, which is a finding about resilience, not something to push through |

## What this execution owes the report

| Report section | Expected to produce |
| :--- | :--- |
| §3.1 · §3.2 | run matrix and the frontier chart |
| §3.3 | knee · sweet spot · waste boundary, and the gap cost between them |
| §3.4 | warm-up share at lowest and highest N — the U-curve mechanism |
| §3.5 | constraint ladder, Tier 1 proven; Tier 2 only if observed |
| §4.2 · §4.3 · §4.4 | marginal decomposition, amortization, Fargate break-even |
| §5 | guardrails on N and on worker memory limits |

---

# 2 · Journal

## How a point is run

One invocation. The script does preflight, window timing, interruption detection,
`points_count`, export, Qdrant reset, and emits the point block.

```bash
../../scripts/run-point.py --run ingestion-n04 --n 4 --doc-count ⟨00-baseline Constants⟩
```

| Exit | Meaning | Next action |
| :--- | :--- | :--- |
| 0 | clean | paste the block, then read the saturation signal in Grafana **now** → M5 |
| 1 | preflight failed | nothing ran |
| 2 | export gaps, **nothing wiped** | do not start the next point — the window is still inside retention |
| 3 | interruptions, point suspect | apply the node-loss rule above |
| 4 | timeout, nothing exported | point lost |

## Points

| Point | Date UTC | Window | Config commit | Valid | Data |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ingestion-n04` | | | | | |
| `ingestion-n12` | | | | | |
| `ingestion-n24` | | | | | |
| `ingestion-n⟨⟩` | | | | | |
| `ingestion-n⟨⟩` | | | | | |

## Coarse pass — read the shape, then choose

| What the three points show | Refine with |
| :--- | :--- |
| minimum at N=12 | N=8, N=16 |
| minimum at N=4 — range boundary, **not proven** | N=2, N=8 |
| minimum at N=24 — range boundary, **not proven** | N=16, N=32 |
| still falling at N=24 | **the range was wrong** — N=32, N=48 |

Decision after coarse pass: ⟨⟩

### ⟨point blocks pasted here⟩

## Anomalies and validity decisions

| Point | Anomaly | Rule applied | Decision |
| :--- | :--- | :--- | :--- |
| | | | |

---

# 3 · Results

| Block | Present | Feeds |
| :--- | :--- | :--- |
| Matrix | yes | report §3.1–§3.3 |
| Metrics — figures | yes | report §3.4 · §4.2–§4.4 |
| Saturation | yes | report §3.5 |
| Guardrails | yes | report §5 |
| Constants · Applicability | no — adds conditions only, listed in §1 | |
| Routing · Open · Retro | yes | |

---

## Matrix

**Finding:** ⟨one sentence — throughput plateaus at N=⟨⟩, unit cost bottoms at N=⟨⟩⟩

| N | Docs/min | Wall | Node-h Spot | Node-h On-Dem | $/run | $/1M docs | Source | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | | | |
| 12 | | | | | | | | |
| 24 | | | | | | | | |
| ⟨⟩ | | | | | | | | |
| ⟨⟩ | | | | | | | | |

| Field | Value |
| :--- | :--- |
| Knee | N=⟨⟩ — last point with a meaningful docs/min gain · threshold used ⟨⟩ |
| Sweet spot | N=⟨⟩ — minimum `$/1M docs` |
| Waste boundary | N=⟨⟩ — `$/run` up substantially, throughput up under 10 % |
| Gap cost | ⟨⟩ extra per 1M docs paid at the knee versus the sweet spot |
| Reference value | ⟨the pre-sweep default N⟩ · Fargate equivalent below |
| Raw data | `./data/frontier.csv` · chart by `./scripts/plot-frontier.py` |

---

## Metrics — figures

| Figure | Formula | Inputs | Value |
| :--- | :--- | :--- | :--- |
| Docs/min | `doc_count ÷ wall_time` | `00-baseline` Constants · run log | |
| Drain-rate cross-check | derivative of E1 | E1 | |
| Node-hours | E2 integrated over the window, **Spot and On-Demand never summed** | E2 · run log | |
| `$/run` | `node_h_spot × price_spot + node_h_od × price_od` | node-hours · `00-baseline` price basis → M4 | |
| `$/1M docs` | `$/run ÷ doc_count × 1e6` | `$/run` · Constants | |
| Warm-up share | `((E3 → E4) + consolidation tail) ÷ total node-hours` | E3 · E4 · E2 | |
| Marginal decomposition | chunker · indexer · TEI share · warm-up · SQS · S3 · NAT — components sum to the total, **floor lines excluded** | `$/run` · E5 · price basis → M6 | |
| Amortization | `(Block B + marginal × V) ÷ V` across volumes | marginal · `00-baseline` floor → M6 | |
| Fargate equivalent | `vCPU-h × rate + GB-h × rate` from frozen pod requests × node-hours | node-hours · Constants · price basis | |

All rows above are derived. Sources feeding them are marked in the Matrix.

---

## Saturation

| Axis value | Component at its ceiling | Evidence | Relieved by |
| :--- | :--- | :--- | :--- |
| low N | ⟨expected: chunker⟩ | E10 at the frozen limit | more workers at higher N |
| high N | ⟨Tier 2 — only if observed⟩ | E20 · E21 · E30 | ⟨not attempted⟩ |

> A tier counts as proven only when the previous ceiling was actually relieved and a new one
> was then observed — `methodology.md` §9. A point with no recorded saturation signal
> contributes its cost row and nothing to this table → M5.

---

## Guardrails

| Value | Where it is set | From |
| :--- | :--- | :--- |
| `maxReplicaCount: ⟨n⟩` | KEDA ScaledJob, both stages | Matrix — sweet spot |
| chunker `memory.limit: ⟨⟩` | `deploy/k8s/apps/chunker` | E11 peak + headroom ⟨⟩ |
| indexer `memory.limit: ⟨⟩` | `deploy/k8s/apps/indexer` | E11 peak + headroom ⟨⟩ |
| `consolidateAfter: ⟨⟩` | `apps-compute` NodePool | warm-up share, if the tail proves material |

Rows whose source number does not survive the runs are deleted, not left blank.

---

## Routing

| Result | Destination | Applied |
| :--- | :--- | :--- |
| Run matrix, publishable columns | report §3.1 | |
| Frontier chart | report §3.2 | |
| Knee · sweet spot · waste boundary | report §3.3 + guardrail | |
| Warm-up share | report §3.4 | |
| Constraint ladder | report §3.5 | |
| Marginal · amortization · Fargate equivalent | report §4.2–§4.4 | |
| Peak RSS → memory limits | report §5 | |
| Validity columns and per-point journals | stay here — `benchmarks/` only if v1.1 needs a revision-to-revision diff | |

---

## Open

| Item | What it invalidates if wrong | Resolved |
| :--- | :--- | :--- |
| E5 separates NAT-bound from cluster-internal egress | one line of the marginal decomposition, silently | |
| Spot price during the run windows matches the frozen basis | every `$/run` | |
| ⟨E20 · E21 · E30 landed⟩ | Tier 2 only | |

---

## Retro

| Field | Value |
| :--- | :--- |
| Expectation | ⟨held · **inverted** — what actually saturated, in the words that go into the report⟩ |
| Cost against estimate | |
| What should have been checked earlier | ⟨and which validity criterion should have caught it⟩ |
| What belongs back in the kit | |
