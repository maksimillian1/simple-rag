# Execution · 01 · Ingestion concurrency

| | |
| :--- | :--- |
| Produces | ⟨decided at Close — see §3⟩ · expected: report §3 in full, plus the marginal coefficient §4.2 consumes |
| Preconditions | `00-baseline` §7.6 gate rows §2, §7.2-required, §7.3 green. **Not** §7.4 — Cost Explorer data is not an input to this run |
| Data | `./data/` — one `⟨point⟩.point.md` and one export per point |
| Scripts | `./scripts/queries.txt` — pinned to the data beside it. Driver is `../../scripts/run-point.py` |
| Metrics | `./metrics.md` — series read, derived figures, hand-recorded fields |
| Status | ⟨planned · running · closed · abandoned⟩ |

> **Three phases. The Plan is frozen before the first point and is not edited afterwards.**
> A plan written after the result cannot support a recorded hypothesis, and the recorded
> hypothesis is what makes an inverted finding credible instead of embarrassing. If the plan
> turns out wrong, say so in Close — do not rewrite §1.
>
> **Where the result lands is decided at Close**, against the finished report.

---

# 1 · Plan  *(frozen ⟨date⟩)*

### What this execution measures

How ingestion throughput and unit cost respond to ingestion concurrency, over a frozen
corpus, on a Spot NodePool that scales to zero. It answers the engineering question — *how
do we configure it?* — and supplies §4 with one number it cannot compute itself: the
marginal cost per document at the best setting. The finding it exists to produce is that
throughput plateaus at one concurrency level and unit cost bottoms out at a different,
usually lower one.

### Axis and points

| | |
| :--- | :--- |
| Varied | KEDA `maxReplicaCount` (N) on ⟨indexer only / both stages — `00-baseline` §2⟩ |
| Candidate grid | N ∈ {4, 8, 12, 16, 20, 24} |
| Executed | **coarse to fine** — {4, 12, 24} first, then two refinement points chosen from the grid by the shape those three produce. Five points total |
| Held constant | image digests · corpus · TEI replicas · Qdrant config · instance types · every row of `00-baseline` §2 |

A linear sweep of six spends its entire budget before revealing the one failure that matters
most: that the range itself was wrong, because unit cost was still falling at the top of it.
Coarse-to-fine reveals that on the third run and reads as a refinement pass rather than as a
mistake.

**Config commit moves between points and that is expected** — the swept value lives in Git.
What must stay identical is the pair of image digests, frozen against a recorded baseline.

### Conditions

Baseline envelope applies in full (`00-baseline/index.md` §6). This execution adds:

> Bulk-drop arrival pattern — the whole corpus uploaded at once, not a steady stream.
> Between points: both SQS queues at depth zero, `apps-compute` at zero nodes, Qdrant
> collection wiped.

**Two conditions that are conclusions in disguise:**

*Worker packing density.* ≈ ⟨n⟩ workers per node follows from the pinned instance type and
the frozen resource requests. Denser packing amortises per-node warm-up across more work and
shifts the sweet spot to the right. Every figure in §3 is conditional on this ratio, and it
belongs in the report Envelope, not in a footnote.

*Which `ScaledJob` N applies to.* Fixed before the first point and following from the
hypothesis below. A knob on a component that is not the constraint produces a flat curve and
spends the sweep for nothing.

### Window rule

| | |
| :--- | :--- |
| Opens | first `s3:ObjectCreated` — timestamp written to a marker file by the bulk upload script, consumed by `run-point.py --start-marker`. Upload itself is outside the system under test |
| Closes | `apps-compute` NodePool at **zero nodes**, plus a 5-minute buffer |

**The window does not close when the queues drain.** Nodes bill through `consolidateAfter`
and teardown, producing zero documents at full price — and that tail is precisely what makes
unit cost turn back up at high N. Closing on "queue empty" silently deletes the mechanism
report §3.4 exists to demonstrate. `run-point.py` enforces this; do not override it.

### Validity criteria

- [ ] Identical across points: image digests, corpus snapshot, `00-baseline` §2 values
- [ ] Reset between points: both queues to zero depth, `apps-compute` to zero nodes, Qdrant
  collection recreated (`--wipe-mode recreate`)
- [ ] Docs/min agrees within a few percent between its two independent sources — wall clock
  over the frozen corpus (C1) and the derivative of queue depth (C2). Disagreement means the
  run stalled and recovered rather than draining steadily; the point is not trusted
- [ ] `points_count` at the end of the run equals the corpus document count. A short count
  means documents were dropped and the denominator lies
- [ ] **Node loss during the run** → the point carries warm-up cost that belongs to no
  concurrency level. Either re-run it, or mark `$/1M docs` ᴱ and exclude it from the curve
  fit. Averaging it in silently is not a defensible third option

### Instrumentation

Full detail in `./metrics.md`. Names live in `00-baseline/metrics.md` — referenced, never
redefined.

| Ref | Read as | Gates |
| :--- | :--- | :--- |
| E1 | queue drain over time | C2 cross-check · saturation candidate |
| E2 | billable nodes over the window, by capacity type | C3 → C4 → C5 — every cost figure |
| E3, E4 | warm-up window per node | C6 → report §3.4, the U-curve mechanism |
| E5 | egress bytes | the NAT line of report §4.2 |
| E10 | worker CPU against limit | **Tier 1 proof** |
| E11 | worker peak RSS | two guardrail rows |
| E20, E21, E30 | TEI and Qdrant saturation | report §3.5 Tier 2 — optional, one claim |

Query file: `./scripts/queries.txt` · dry run clean: ⟨date⟩

### Hypothesis  *(recorded ⟨date⟩, before the first point)*

**Tier 1 will be the Stage-1 chunker, not TEI.** PyMuPDF text extraction on a 300-page PDF
is single-threaded CPU work and may dominate embedding time by an order of magnitude. The
original design assumed inference would saturate first.

Corollary expected: unit cost minimum below the throughput knee, with the gap driven by
warm-up share (C6) rather than by any component ceiling.

If this inverts, the inversion goes into the report verbatim. *"We expected to saturate
inference and saturated PDF parsing instead"* is what makes a measurement credible.

### Cost and stop condition

| | |
| :--- | :--- |
| Estimated cost | 5 points × ⟨wall time⟩ · ⟨$⟩ ᴱ, Spot |
| Stop if | three consecutive points are invalidated by node loss — the Spot pool cannot hold a run long enough to measure, which is itself a finding for the reliability execution, not something to push through |

---

# 2 · Journal

## How a point is run

One invocation. The script does preflight, window timing, interruption detection,
`points_count`, export, Qdrant reset, and emits the point block.

```bash
../../scripts/run-point.py --run ingestion-n04 --n 4 --doc-count ⟨00-baseline §3⟩
```

Exit codes: `0` clean · `1` preflight failed · `2` export gaps, **nothing wiped** ·
`3` interruptions, point suspect · `4` timeout, nothing exported.

Then, by hand and only by hand:

1. **R2 · saturation signal** — read E10 / E20 / E30 in Grafana *now*, while the window is
   fresh. No query returns "the chunker was the bottleneck". Write it into the block.
2. Paste `./data/ingestion-n⟨nn⟩.point.md` under the matching heading below.

> On exit code 2: do not start the next point. Prometheus retention is ⟨3 d⟩, the window is
> still recoverable, and the collection has deliberately not been wiped.

## Points

| Point | Date UTC | Config commit | Outcome | Data |
| :--- | :--- | :--- | :--- | :--- |
| `ingestion-n04` | | | | |
| `ingestion-n12` | | | | |
| `ingestion-n24` | | | | |
| `ingestion-n⟨⟩` | | | | |
| `ingestion-n⟨⟩` | | | | |

### Coarse pass — read the shape, then choose

| What the three points show | Refine with |
| :--- | :--- |
| `$/1M docs` minimum at N=12 | N=8, N=16 |
| minimum at N=4 — range boundary, **not proven** | N=2, N=8 |
| minimum at N=24 — range boundary, **not proven** | N=16, N=32 |
| still falling at N=24 | **the range was wrong** — N=32, N=48 |

Decision after coarse pass: ⟨⟩

### `ingestion-n04`

⟨paste block⟩

### `ingestion-n12`

### `ingestion-n24`

### `ingestion-n⟨⟩`

### `ingestion-n⟨⟩`

## Anomalies and validity decisions

| Point | Anomaly | Rule applied | Decision |
| :--- | :--- | :--- | :--- |
| | | | |

State the rule, not just the outcome. "Re-run" and "excluded and marked ᴱ" are both
defensible; averaging an anomalous point in silently is not.

---

# 3 · Close

## Result matrix

Assembled from §2. The seven-column form goes to report §3.1; the validity columns stay
here.

| N | Config commit | Docs/min | Wall | Node-h Spot | Node-h On-Dem | $/run | $/1M docs | Saturation (R2) | Interrupts | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | | | | | |
| 12 | | | | | | | | | | |
| 24 | | | | | | | | | | |
| ⟨⟩ | | | | | | | | | | |
| ⟨⟩ | | | | | | | | | | |

Derived — all ᴬ:

| | Value | From |
| :--- | :--- | :--- |
| Knee | N=⟨⟩ | last point with a meaningful docs/min gain — threshold used: ⟨⟩ |
| Sweet spot | N=⟨⟩ | minimum `$/1M docs` (C5) |
| Waste boundary | N=⟨⟩ | `$/run` up substantially, throughput up under 10 % |
| Gap cost | ⟨⟩ | extra `$/1M docs` paid at the knee versus the sweet spot |
| Tier 1 constraint | ⟨⟩ | R2 at low N |
| Tier 2 constraint | ⟨⟩ | R2 after Tier 1 relieved — **only if E20/E30 landed and it was observed** |
| Warm-up share, lowest vs highest N | ⟨⟩ / ⟨⟩ | C6 |

## Export manifest

| Artifact | Written | Gaps | Notes |
| :--- | :--- | :--- | :--- |
| `./data/ingestion-n⟨nn⟩.point.md` × 5 | | | |
| Prometheus exports per point | | | retention ⟨3 d⟩ — exported after each point |
| `./data/frontier.csv` | | | input to the report chart |
| `./scripts/plot-frontier.py` + rendered chart | | | report §3.2 |

## Routing — where the result went

Decided here, against the finished report.

| Destination | When it applies | Used |
| :--- | :--- | :--- |
| **The whole report** | this is the only execution | no — `00-baseline` §5 is also in it |
| **A report section**, table inline | the material is significant and fits | ⟨expected: §3.1–§3.5, and the coefficient §4.2 consumes⟩ |
| **A benchmark**, cited from a section | too detailed for the report, or needed as the regression unit across revisions | ⟨only if the validity columns must travel with the matrix⟩ |
| **`00-baseline` sections** | it is a given, not a finding, with two or more consumers | ⟨e.g. a resource limit that stops being an axis⟩ |
| **Nothing** | measured, and insignificant against the rest — or the hypothesis did not hold | |

> **Do not create `benchmarks/` speculatively.** Detail is the trigger, not the existence of
> the folder. A five-row matrix fits in §3; it moves out when it grows per-point journals or
> when v1.1 needs to diff against it revision to revision.

| Result | Destination | Applied |
| :--- | :--- | :--- |
| Run matrix (7 columns) | report §3.1 | |
| Chart | report §3.2 | |
| Knee / sweet spot / waste boundary | report §3.3 + guardrail §5 | |
| Warm-up decomposition (C6) | report §3.4 | |
| Constraint ladder | report §3.5 | |
| Marginal decomposition (C7) | report §4.2 | |
| Amortization (C8) | report §4.3 | |
| Fargate equivalent (C9) | report §4.4 | |
| Peak RSS → memory limits (E11) | report §5 guardrails | |

## Hypothesis outcome

- [ ] Confirmed — Tier 1 is the chunker
- [ ] Inverted — ⟨what actually happened; this goes into the report verbatim⟩
- [ ] Untestable — ⟨why⟩

## Retro

- What did this execution cost against its estimate?
- Which precondition should have been checked earlier?
- Which run was wasted, and which gate should have caught it?
- What belongs back in `report-kit`?
