# simple-rag — Execution Log · report v1.0

Working document, not a deliverable. Part 1 is filled once, Part 2 is duplicated per run
point, Part 3 closes the report. Metric references (E1–E17, P1–P3, C1–C9, R1–R4) are
defined in `metrics.md` — read it once before Phase 1.

All timestamps **UTC**. This is the audit trail behind `report.md`.

---

# Part 1 · Preparation

Filled once. Nothing in Part 2 starts until 1.5 is green.

## 1.1 Bindings

| | |
| :--- | :--- |
| System | `simple-rag` — RAG ingestion + query feature on shared EKS |
| Artifact under test | image digests: api ⟨⟩ · chunker ⟨⟩ · indexer ⟨⟩ |
| Ingestion unit of work | ⟨one sentence, incl. when it counts as done⟩ |
| Query unit of work | ⟨one sentence⟩ |
| Workload fixture | `zabiullah/pdf-books-collection`, snapshot ⟨path⟩ |
| Frontier X axis | KEDA `maxReplicaCount`, N ∈ {4, 8, 12, 16, 20, 24} |
| **Run start signal** | first `s3:ObjectCreated` event — timestamp written by the upload script |
| **Run end signal** | `apps-compute` NodePool at **zero nodes**, plus 5 min buffer |
| Unit count source | frozen fixture — exact document count from R2 |
| Region / price basis | ⟨region⟩ · price list retrieved ⟨date⟩ |
| Cost data source | AWS Cost Explorer, tag-based |

> **The end signal is not "queue empty".** Karpenter bills through `consolidateAfter` and
> teardown, and that tail is what makes unit cost turn back up at high N — the mechanism
> §3.4 exists to demonstrate. Close on capacity zero plus buffer. Extra points in an
> export are harmless; missing ones require re-running the point.

## 1.2 Phase 0 · Cost attribution

Not retroactive. Nothing here can be fixed later.

- [ ] `default_tags` in `terraform/envs/prod/providers.tf` with `Project = simple-rag`,
  `Component` (`platform` / `database` / `ingest`), `CostGroup = benchmark`
- [ ] Applied and rolled out — every module overrides `Component` correctly
- [ ] Tags **activated** in Billing → Cost Allocation Tags. Separate step from tagging,
  forward-only, up to 24h before data appears
- [ ] Verified on a live resource in the console, not in plan output
- [ ] Price snapshot captured → 1.4 / R1

Date attribution went live: ⟨⟩

> Without activation, Cost Explorer returns one undifferentiated number and the
> A / B / C floor split in §4.1 is impossible.

## 1.3 Phase 1 · Observability readiness

A component that is not scraped cannot be named as the constraint, and a missing series
looks exactly like an idle one.

**Already scraped — verify only:**

- [ ] `up == 0` returns empty
- [ ] E1 SQS depth · E2 node inventory · E3 node created · E6 worker CPU ·
  E7 worker RSS · E17 Cilium egress

**Blockers — no ServiceMonitor yet.** Add in each component's namespace with
`labels.release` matching the Helm release, then confirm `up{job="…"}`:

- [ ] **E4, E5** — Karpenter: node lifecycle + Spot interruption events
- [ ] **E8, E9, E10** — TEI: queue size, inference duration, batch size
- [ ] **E11, E12, E13** — Qdrant `/metrics` on 6333: write latency, RSS, points count
- [ ] **E14, E15** — Go API: latency histogram, error rate

> These seven are not optional. E1 tells you *that* scaling stopped; only E8–E13 tell you
> *what* stopped it. Without them §3.5 collapses to one unproven guess and Tier 2 — the
> reason for sweeping six points instead of four — cannot be claimed at all.

**Confirmed metric names.** Curl each `/metrics` endpoint once and copy the real name.
A wrong name returns NO DATA and is indistinguishable from a missing target.

| Ref | Name as exposed |
| :--- | :--- |
| E4 | |
| E5 | |
| E8 | |
| E9 | |
| E10 | |
| E11 | |
| E12 | |
| E13 | |
| E14 | |
| E16 | |

- [ ] `scripts/queries.txt` written using confirmed names only
- [ ] `./export-metrics.py --run smoke --last 10m --dry-run` → zero NO DATA, zero unknown
  metric names
- [ ] Prometheus `retention: 3d` noted — export after **every** point, no exceptions

## 1.4 Recorded before any run

Unrecoverable. No tool produces these.

**R1 · Price snapshot** — dated, committed to `cost-model.xlsx`.

- [ ] Every instance type Karpenter may select in `apps-compute` and `apps-serving`,
  **spot and on-demand**, $/hour
- [ ] `core-on-demand` and `database-on-demand` instance types, $/hour
- [ ] NAT Gateway — $/hour and $/GB processed
- [ ] VPC Interface Endpoints — $/hour per endpoint per AZ (Bedrock, SQS, S3)
- [ ] EBS gp3 — $/GB-month
- [ ] EKS control plane — $/hour
- [ ] S3 Standard + Glacier Instant Retrieval, SQS requests
- [ ] **Fargate — $/vCPU-hour and $/GB-hour** (needed for the §4.4 comparison)

Date retrieved: ⟨⟩

**R2 · Fixture profile** — from the local PyMuPDF script, output committed to
`docs/report/data/corpus-profile.txt`.

| | |
| :--- | :--- |
| File count | |
| **Exact document count** | ← the denominator of C1 and C5 |
| Pages: median · p95 · total | |
| Characters: total · median per file | |
| Total bytes | |
| Snapshot location and freeze date | |

## 1.5 Go / no-go gate

All of 1.2–1.4 green? Date: ⟨⟩

If a blocker in 1.3 is unresolved: name the section that loses its evidence and record
the decision here. Do not drift into it silently.

Unresolved blockers and their cost: ⟨⟩

---

# Part 2 · Run journal

## 2.0 Point template — copy for each N

````
### E1 · N=⟨⟩

Pre-flight
- [ ] Both SQS queues at depth zero (verified by query)
- [ ] apps-compute NodePool at zero nodes (verified by query)
- [ ] Image digests unchanged since previous point
- [ ] Fixture unchanged — same snapshot, same bytes
- [ ] Only maxReplicaCount differs

Config commit: ⟨sha⟩
Window UTC:    start ⟨⟩ → end ⟨⟩   (NodePool zero + 5 min)

Results
| | |
| :--- | :--- |
| Docs/min — wall clock ÷ doc count | |
| Docs/min — SQS depth derivative | |
| Cross-check within a few percent? | |
| Wall time | |
| Node-hours spot, by instance type | |
| Node-hours on-demand, by instance type | |
| $/run | |
| $/1M docs | |

R4 · Saturation signal: ⟨component⟩ — read from ⟨metric ref⟩ at ⟨value⟩
    Candidates: chunker CPU (E6) · TEI queue (E8) · Qdrant write latency (E11)
                · SQS not draining despite idle workers (E1)

Anomalies
- Spot interruptions: ⟨n⟩            (E5)
- Other — stuck retries, OOM, manual intervention: ⟨⟩

Validity
- [ ] Valid — include in curve fit
- [ ] Re-run required — reason: ⟨⟩
- [ ] Marked ᴱ and excluded from fit — reason: ⟨⟩

Export
- [ ] docs/report/data/e1-n⟨⟩.jsonl written, non-empty
- [ ] e1-n⟨⟩.meta.json present, gaps: []

Reset before next point
- [ ] Both queues drained to zero
- [ ] apps-compute back to zero, confirmed by query
- [ ] Qdrant state handled per the standing decision in 2.8

Notes:
````

## 2.1 E1 · N=4

*(paste template)*

## 2.2 E1 · N=8

## 2.3 E1 · N=12

## 2.4 E1 · N=16

## 2.5 E1 · N=20

## 2.6 E1 · N=24

## 2.7 Conditional seventh point

Triggered only if the `$/1M docs` minimum lands on N=4. A minimum on the range boundary
is not proven — there is no descending branch to its left.

- [ ] Not triggered
- [ ] Triggered → run N=1 or N=2, paste the template above

## 2.8 Standing decision — Qdrant state between points

- [ ] Collection wiped between points
- [ ] Collection retained and allowed to grow across points

Either is defensible; changing it mid-sweep is not. Copy the decision into the report
Envelope (§2.3).

> A growing collection raises write latency — which is exactly the E11 signal Tier 2 may
> rest on. Retaining state contaminates the constraint ladder; wiping costs time between
> points. Decide once, before N=4.

Decision: ⟨⟩ · Rationale: ⟨⟩

## 2.9 E2 · Idle floor window *(24h, passive — schedule first, run alone)*

- [ ] Scheduled so that **no sweep point falls inside it**. One point inside destroys the
  window and costs a full day
- [ ] Zero workload and zero human activity: no deploys, no config changes, no manual
  commands. ArgoCD reconciliation stays on — it is part of the floor
- [ ] Window spans a full daily cycle: backups, rotations, scheduled jobs

Window UTC: start ⟨⟩ → end ⟨⟩

**P1 · Spend by tag, daily granularity, grouped by `Component`:**

| Component tag | $/day | → Block |
| :--- | :--- | :--- |
| `platform` | | A |
| `database` | | B |
| `ingest` | | B |
| untagged / shared | | ⟨resolve before writing §4.1⟩ |

**Blocks:** **A** shared platform (exists without this feature) · **B** feature-dedicated
(disappears with it — **this is the BLUF number**) · **C** = A + B, the standalone
greenfield scenario.

**Always-billed lines — audit each explicitly.** Mark ᴬ for anything computed from R1
rather than resolved from the bill.

Block A:
- [ ] EKS control plane
- [ ] `core-on-demand` node group — CoreDNS, ArgoCD, Cilium, Prometheus, Grafana
- [ ] NAT Gateway — hourly
- [ ] NAT Gateway — per-GB processed (cross-check against E17)
- [ ] EBS gp3 — Prometheus 10Gi + Loki 10Gi

Block B:
- [ ] `database-on-demand` node group — Qdrant
- [ ] EBS gp3 — Qdrant volume
- [ ] VPC Interface Endpoints — Bedrock, SQS, S3 × AZ count
- [ ] TEI serving capacity at idle — **confirm whether it actually scales to zero**
- [ ] S3 storage — raw + Glacier IR after 7d
- [ ] SQS requests
- [ ] KEDA ScaledJob ingestion compute — expected 0.00, the one genuinely zero row

Untagged spend resolved? ⟨⟩

> The NAT Gateway is the hidden line of this architecture class and is omitted from
> almost every published version of it. It bills hourly regardless of traffic, and again
> per GB — including image pulls and the indexer's HuggingFace weight downloads.

## 2.10 E4 · Query load

Requires E14, E15 scraped.

| RPS | p50 | p95 | p99 | Qdrant search latency (E11) | Error rate (E15) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| ⟨low⟩ | | | | | |
| ⟨mid⟩ | | | | | |
| ⟨high⟩ | | | | | |

Window UTC per level: ⟨⟩
Export: `docs/report/data/e4-⟨rps⟩.jsonl`

**Combined-load point** — mid RPS while ingestion runs at the sweet-spot N. The only
measurement that shows whether the two paths contend on Qdrant.

- [ ] Run · p95 ⟨⟩ · delta vs the idle-cluster row ⟨⟩
- [ ] Skipped — record in 3.2

Article 1 claimed p95 < 200 ms. This table confirms it under load or replaces it.

## 2.11 E5 · Quantization *(local, no cluster cost)*

Ground truth is the system's own float32 index — no labelled dataset needed.

- [ ] float32 index built · Qdrant RSS ⟨⟩ (E12)
- [ ] INT8 scalar-quantized index built · Qdrant RSS ⟨⟩ (E12)
- [ ] ~200 queries against both, top-10 overlap ⟨⟩ %
- [ ] Comparison script committed to `scripts/`
- [ ] Smallest viable instance class per variant, priced from R1

Arithmetic reference, defensible in advance: 1M points × 384 dim × 4 B = 1.536 GB ᴬ;
INT8 → 0.384 GB ᴬ. Everything else comes from the run.

---

# Part 3 · Close

## 3.1 Result matrix

Assembled from Part 2. Goes into `report.md` §3.1 verbatim.

| N | Config commit | Docs/min | Wall | Node-h spot | Node-h on-dem | $/run | $/1M docs | Saturation | Interrupts | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | | | | | |
| 8 | | | | | | | | | | |
| 12 | | | | | | | | | | |
| 16 | | | | | | | | | | |
| 20 | | | | | | | | | | |
| 24 | | | | | | | | | | |

Derived — all ᴬ:

| | Value | From |
| :--- | :--- | :--- |
| Knee | N=⟨⟩ | last point with a meaningful docs/min gain — threshold used: ⟨⟩ |
| Sweet spot | N=⟨⟩ | minimum `$/1M docs` |
| Waste boundary | N=⟨⟩ | `$/run` up substantially, throughput up under 10 % |
| Gap cost | ⟨⟩ | extra $/1M docs paid at the knee versus the sweet spot |
| Tier 1 constraint | ⟨⟩ | R4 at low N |
| Tier 2 constraint | ⟨⟩ | R4 after Tier 1 relieved by higher N — **only if actually observed** |
| Warm-up share, N=4 vs N=24 | ⟨⟩ / ⟨⟩ | C6 |

**Hypothesis check** — recorded before the runs: Tier 1 was expected to be the **Stage-1
chunker**, not TEI. PyMuPDF extraction on a 300-page PDF is single-threaded CPU work and
may dominate embedding time by an order of magnitude. The original design assumed
inference would saturate first.

- [ ] Confirmed
- [ ] Inverted → keep the inversion in the report. *"We expected to saturate inference and
  saturated PDF parsing instead"* is what makes the measurement credible

## 3.2 Skip log

Copy into `report.md` §2.3 Envelope and its "Not covered" table.

| Skipped | Section affected | Reason |
| :--- | :--- | :--- |
| Spot interruption injected under load (E3) | reliability economics | needs its own run and its own instrumentation — deferred to v2.0 |
| Per-execution worker exit summaries | per-worker attribution | not needed: counts come from the frozen fixture, drain rate from E1, interruptions from E5 |
| Third constraint tier | §3.5 | never claimed speculatively |
| Regression vs previous report | — | unavailable at v1.0, no `Supersedes` |
| | | |

## 3.3 Report integrity gate

- [ ] Every number traceable to a file in `docs/report/data/`
- [ ] Every non-measured number marked ᴬ / ᴹᵒ / ᴱ; convention stated once in the header
- [ ] No ⟨⟩ placeholder survives in `report.md`
- [ ] "Open decisions" block deleted from `report.md`
- [ ] BLUF written **last**, from finished numbers; every row carries a reference value
  and a plain-language meaning; the verdict names one action
- [ ] Every guardrail is a config value with a source and a file — no blank rows
- [ ] Every section yields at least one number reaching BLUF or Guardrails
- [ ] No third tier · no priced SLA breach · no closing "future work" list
- [ ] Invalid points excluded from the curve fit, and the exclusion stated
- [ ] The unqualified "$0.00 idle" claim from article 1 is retired by §4.1 — as a
  deepening with data in hand, not as a correction

## 3.4 Retro

- Which missing item cost the most time?
- Which run was wasted, and which gate should have caught it?
- Kit fixes to port back to `report-kit`:

**Article 2 positioning** — article 1 sold the architecture, article 2 sells the
economics. Do not make it technically deeper; make it about money. Sections most likely
to travel: the honest floor breakdown (§4.1), the knee/sweet-spot gap (§3.3–3.4), and the
Spot-versus-Fargate arithmetic (§4.4).
