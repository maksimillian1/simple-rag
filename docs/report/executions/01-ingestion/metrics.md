# Execution · 01 · Ingestion concurrency — Instrumentation

> Belongs to `index.md` §1 Plan. Extracted because it is long. **Frozen with the Plan,
> before the first point.**

Scope: **what this run reads and how**. The metric names themselves are a property of the
system and live in `00-baseline/metrics.md` — referenced here, never redefined.

---

## Series read

| Ref | Read as | Filter | Gates |
| :--- | :--- | :--- | :--- |
| E1 | queue depth over the window; its derivative is the drain rate | per queue — never summed | C2 · the "queue not draining despite idle workers" saturation reading |
| E2 | billable nodes at each moment, by capacity type | `label_karpenter_sh_nodepool="apps-compute"` | C3 → C4 → C5. **Without it there is no cost figure at all** |
| E3 | node creation timestamp | same node selector | C6 |
| E4 | first-pod-ready timestamp | pods owned by the ingestion `ScaledJob`s | C6 → report §3.4. Without it the U-curve has a shape and no mechanism |
| E5 | egress bytes over the window | ⟨NAT-bound selector — `00-baseline` §7.5⟩ | the NAT data-processing line of C7 |
| E10 | worker CPU as a fraction of the frozen limit | `namespace` + per-component `container` | **Tier 1 proof** (report §3.5) |
| E11 | worker peak working set | as E10 | two memory guardrails (report §5) |
| E20 | TEI queue depth | job selector | report §3.5 Tier 2 — **one claim only** |
| E21 | TEI inference duration | job selector, histogram | report §3.5 Tier 2 |
| E30 | Qdrant write / upsert latency | job selector | report §3.5 Tier 2 |

**Required:** E1, E2, E3, E4, E10, E11 — these gate the run itself. A point missing any of
them has no cost, no mechanism or no Tier 1 and is not worth its cluster time.

**Optional:** E5 (degrades one line of C7 to ᴬ from the price list), E20, E21, E30 (gate
Tier 2 and nothing else). A campaign that waits on a nice-to-have is a campaign that does
not happen.

**Read once per point over REST, not scraped:** Qdrant `points_count` at the end of the
window, by `run-point.py` — the completeness check against the corpus document count.

Query file: `./scripts/queries.txt` — one line per series, written with confirmed names
only · dry run clean: ⟨date⟩

> Prometheus retention is ⟨3 d⟩. **Export after every point, no exceptions.** Extra points in
> an export are harmless; missing ones require re-running at full cost.

---

## Derived figures

Computed, not measured. Everything here carries ᴬ in the report.

| Ref | Definition | From |
| :--- | :--- | :--- |
| C1 | docs/min = `doc_count ÷ wall_time` | `00-baseline` §3 · R1 |
| C2 | throughput cross-check = derivative of E1 | E1 |
| C3 | node-hours per point = E2 integrated over the window, **Spot and On-Demand kept separate** | E2 · R1 |
| C4 | `$/run = node_hours_spot × price_spot + node_hours_od × price_od` | C3 · `00-baseline` §4 |
| C5 | `$/1M docs = $/run ÷ doc_count × 1e6` | C4 · `00-baseline` §3 |
| C6 | warm-up share = `((E3 → E4) + consolidation tail) ÷ total node-hours` | E3 · E4 · E2 |
| C7 | marginal decomposition at the sweet spot — chunker, indexer, TEI share, warm-up overhead, SQS, S3, NAT; components sum to the total | C4 · E5 · `00-baseline` §4 |
| C8 | effective `$/doc` across volumes = `(Block B floor + C7 × V) ÷ V` | C7 · `00-baseline` §5 |
| C9 | Fargate equivalent = `vCPU-hours × rate + GB-hours × rate`, from the frozen pod requests × C3 | C3 · `00-baseline` §2, §4 |

**Because the NodePool is pinned to one instance type, C4 is a product, not a sum over
types.** That is the whole reason for pinning it beyond comparability.

**C7 excludes every floor line by definition.** Mixing them inflates the coefficient and
silently corrupts the break-even in report §4.4.

**C8 uses Block B, not Block C.** For a feature on a cluster that exists anyway, the question
is what *this feature* costs to keep alive.

---

## Recorded by hand

Unrecoverable. If it is not written down at the time, the point is lost.

| Ref | What | Why nothing else produces it |
| :--- | :--- | :--- |
| R1 | **Run log** — point id, N, config commit, UTC start and end, `points_count`, interruption count, validity decision | Prometheus does not know when a run began, and a window guessed a week later is a different run. *Emitted by `run-point.py`* into `./data/⟨point⟩.point.md` |
| R2 | **Saturation signal** — which component was at its ceiling at this point, and the metric it was read from. Candidates: chunker CPU (E10) · TEI queue depth (E20) · Qdrant write latency (E30) · queue not draining despite idle workers (E1) | No query returns "the chunker was the bottleneck". It is a reading across E10–E30, and it is the entire raw material of the constraint ladder. **The only field of the point block the script cannot fill** — read it in Grafana immediately after the point |

A point with an empty R2 contributes nothing to report §3.5. It still contributes its cost
row, so it is not wasted — but the ladder is built from R2 alone.

---

## Window boundaries

The most commonly mis-set values, and the usual reason a sweep is thrown away. Enforced by
`run-point.py`; stated here because the script encodes the rule and nothing else explains
it.

- **Start** — the first `s3:ObjectCreated` event. The bulk upload script writes this
  timestamp to a marker file consumed by `--start-marker`. Upload itself is outside the
  system under test, and its duration and cost are excluded.
- **End** — `apps-compute` NodePool at **zero nodes**, plus a 5-minute buffer.

The window does not close when the SQS queues drain. Nodes bill through `consolidateAfter`
and teardown, producing zero documents at full price — and that tail is precisely what makes
the unit-cost curve turn back up at high N. Closing on "queue empty" silently deletes the
mechanism the report exists to demonstrate.
