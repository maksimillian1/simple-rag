# simple-rag — Execution Log · report v1.0

Working document, not a deliverable. Part 1 is filled once, Part 2 is duplicated per run
point, Part 3 closes the report. Metric references (E1–E9, P1–P3, C1–C10, R1–R5) are
defined in `metrics.md` — read it once before Phase 1.

All timestamps **UTC**. This is the audit trail behind `report.md`.

---

## Tracks

Two dependency chains, deliberately separated. Track B is not "later" — B1 and B3 are
inputs to Track A and must be done first.

**Track A · Cluster.** Sequential, blocking, costs money, needs a clean cluster and full
attention. Order: 1.2 → 1.3 → 1.6 → 1.7 gate → Part 2 sweep → idle window → teardown.

**Track B · Local.** Parallel, non-blocking, zero cloud cost, laptop only. Nothing in
Track A waits on it beyond B1 and B3, and it waits on nothing.

| | Item | Feeds | Blocked by |
| :--- | :--- | :--- | :--- |
| B1 | R2 fixture profile (PyMuPDF script) | §2.2, denominator of C1/C5 | nothing |
| B3 | R1 price snapshot (pinned instance types only) | all of §4 | instance type pinned (1.6) |
| B5 | Plot script for §3.2 | §3.2 | nothing — write it against fake data now |

> A sweep point without R2 has no denominator and without R1 has no price. Do B1 and B3
> on the same evening, before any Track A run.

---

# Part 1 · Preparation

Filled once. Nothing in Part 2 starts until 1.7 is green.

## 1.1 Bindings

| | |
| :--- | :--- |
| System | `simple-rag` — RAG ingestion feature on shared EKS |
| Artifact under test | image digests: chunker ⟨⟩ · indexer ⟨⟩ — frozen by `run-point.py --set-baseline` |
| Ingestion unit of work | ⟨one sentence, incl. when it counts as done⟩ |
| Workload fixture | `zabiullah/pdf-books-collection`, snapshot ⟨path⟩ |
| Frontier X axis | KEDA `maxReplicaCount` — coarse pass N ∈ {4, 12, 24}, then refinement |
| Runs in scope | `sweep` (ingestion concurrency) · `idle` (24h floor window) |
| **Run start signal** | first `s3:ObjectCreated` event — marker file written by the upload script |
| **Run end signal** | `apps-compute` NodePool at **zero nodes**, plus 5 min buffer |
| Unit count source | frozen fixture — exact document count from R2 |
| Region / price basis | ⟨region⟩ · price list retrieved ⟨date⟩ |
| Cost data source | AWS Cost Explorer, tag-based, `idle` window only |

> **The end signal is not "queue empty".** Karpenter bills through `consolidateAfter` and
> teardown, and that tail is what makes unit cost turn back up at high N — the mechanism
> §3.4 exists to demonstrate. `run-point.py` enforces this; do not override it.

**Dropped from v1.0** — decided, not pending. Do not relitigate.

| Dropped | Why |
| :--- | :--- |
| Query load run and Go API instrumentation | A single fixed-replica latency figure is a number without an axis. The query path has its own frontier (API/TEI replicas × RPS) and does not share a denominator with ingestion |
| Quantization recall study | Scalar Quantization is a **fixed configuration parameter** in v1.0, chosen for memory footprint. Its retrieval cost is not measured here and is explicitly out of scope |
| Spot interruption injection | Needs its own run and its own instrumentation |
| Per-execution worker exit summaries | Counts come from the frozen fixture, drain rate from E1 |
| Third constraint tier | Never claimed speculatively |
| Lambda break-even | The cluster exists regardless; the alternative is Fargate |

## 1.2 Phase 0 · Cost attribution

Not retroactive. Nothing here can be fixed later. **Longest lead time of anything in
Part 1 — do this first.**

- [ ] `default_tags` in `terraform/envs/prod/providers.tf` with `Project = simple-rag`,
  `Component` (`platform` / `database` / `ingest`), `CostGroup = benchmark`
- [ ] Applied and rolled out — every module overrides `Component` correctly
- [ ] Tags **activated** in Billing → Cost Allocation Tags. Separate step from tagging,
  forward-only, up to 24h before data appears
- [ ] Verified on a live resource in the console, not in plan output
- [ ] Price snapshot captured → 1.5 / R1

Date attribution went live: ⟨⟩

> Without activation, Cost Explorer returns one undifferentiated number and the
> A / B / C floor split in §4.1 is impossible.

## 1.3 Phase 1 · Observability readiness

Two states, not one. The sweep does **not** wait on the second.

**Required — verify before the first point:**

- [ ] `up == 0` returns empty
- [ ] E1 SQS depth · E2 node inventory · E3 warm-up window (node created **and**
  pod start) · E4 Cilium egress · E5 worker CPU · E6 worker RSS
- [ ] Confirm the pod-side name for E3 against kube-state-metrics (`kube_pod_start_time`
  or the ready-time variant, depending on version)

**Parallel — required for §3.5 Tier 2 only. Not a gate.**

- [ ] **E7, E8** — TEI: `te_queue_size`, `te_request_inference_duration`
- [ ] **E9** — Qdrant `/metrics` on 6333: write / upsert latency
- [ ] Karpenter ServiceMonitor — **15-minute timebox.** If `serviceMonitor.enabled` in
  the Helm values works first try, take it. Otherwise abandon; `run-point.py` covers
  interruption detection

> Tier 1 reads from E5 and is available today. If TEI and Qdrant land before the
> refinement points, Tier 2 is claimable from the points that have them. If they never
> land, one tier is reported and the second goes to "Not covered" — which is what the
> report already requires of an unproven tier. This is a reduced claim, not a blocked run.

**Confirmed metric names.** Curl each `/metrics` endpoint once and copy the real name.
A wrong name returns NO DATA and is indistinguishable from a missing target.

| Ref | Name as exposed |
| :--- | :--- |
| E3 (pod side) | |
| E7 | |
| E8 | |
| E9 | |

- [ ] `scripts/queries.txt` written using confirmed names only
- [ ] `./export-metrics.py --run smoke --last 10m --dry-run` → zero NO DATA, zero unknown
  metric names
- [ ] Prometheus `retention: 3d` noted — export after **every** point, no exceptions

## 1.4 Tooling readiness

- [ ] `run-point.py` config block filled: both SQS URLs, Qdrant collection, app namespace
- [ ] `./run-point.py --set-baseline` — image digests frozen for the sweep
- [ ] `./run-point.py --run sweep-n04 --n 4 --preflight-only` → clean
- [ ] Bulk upload script writes the first `s3:ObjectCreated` timestamp to a marker file
- [ ] Port-forwards verified, or `--no-port-forward` path confirmed

## 1.5 Recorded before any run

Unrecoverable. No tool produces these.

**R1 · Price snapshot** — dated, committed to `cost-model.xlsx`. Short list because the
NodePools are pinned (1.6).

- [ ] Pinned `apps-compute` instance type — **spot and on-demand**, $/hour
- [ ] Pinned `apps-serving` instance type — spot and on-demand, $/hour
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

## 1.6 Configuration freeze

Decided once, before N=4, and copied into the report Envelope (§2.3). Changing any of
these mid-sweep invalidates the sweep.

| Parameter | Decision | Why it must be frozen |
| :--- | :--- | :--- |
| `apps-compute` instance type | ⟨type⟩ | An unpinned pool makes points non-comparable and silently changes worker packing density — the mechanism §3.4 measures |
| Workers per node (resulting) | ⟨~n⟩ | Dense packing amortises warm-up and shifts the sweet spot right. Record the ratio; it is a condition of the result, not a detail |
| Qdrant `optimizers_config.indexing_threshold` | ⟨value⟩ | HNSW rebuilt during bulk ingest inflates E9 for a reason unrelated to saturation, and would misattribute Tier 2 |
| Scalar Quantization | **on** — fixed parameter, memory footprint only | Retrieval cost not measured in v1.0; stated as a condition, not a finding |
| Qdrant state between points | **wiped** — `run-point.py --wipe-mode recreate` | A growing collection raises write latency, which is exactly the E9 signal Tier 2 may rest on. Retaining state contaminates the constraint ladder |
| Which ScaledJob N applies to | ⟨indexer only / both stages⟩ | Follows from the Tier 1 hypothesis; a knob on a non-constraint produces a flat curve |

Decided by: ⟨⟩ · Date: ⟨⟩

## 1.7 Go / no-go gate

All of 1.2–1.6 green? Date: ⟨⟩

Parallel items from 1.3 still open — list them and note which report claim is at risk:
⟨⟩

---

# Part 2 · Run journal

## 2.0 How a point is run

One invocation. The script does preflight, window timing, interruption detection,
`points_count`, export, Qdrant reset, and emits the point block.

````
./run-point.py --run sweep-n04 --n 4 --doc-count ⟨R2 count⟩
````

Exit codes: `0` clean · `1` preflight failed · `2` export gaps, **nothing wiped** ·
`3` interruptions, point suspect · `4` timeout, nothing exported.

Then, by hand and only by hand:

1. **R4 · saturation signal** — read E5 / E7 / E9 in Grafana *now*, while the window is
   fresh. No query returns "the chunker was the bottleneck". Write it into the block.
2. Paste `docs/report/data/<point>.point.md` under the matching heading below.

> On exit code 2: do not start the next point. Prometheus retention is 3 days, the window
> is still recoverable, and the collection has deliberately not been wiped.

## 2.1 Coarse pass

Three points first. The shape of the curve after three decides where the remaining two go
— and catches the one failure a linear sweep only reveals on the sixth run: that the
range was wrong.

| Point | Ran | Result block pasted |
| :--- | :--- | :--- |
| `sweep-n04` | | |
| `sweep-n12` | | |
| `sweep-n24` | | |

**Read the shape, then choose:**

| What three points show | Refine with |
| :--- | :--- |
| `$/1M docs` minimum at N=12 | N=8, N=16 |
| minimum at N=4 (range boundary — not proven) | N=2, N=8 |
| minimum at N=24 (range boundary — not proven) | N=16, N=32 |
| still falling at N=24 | **the range was wrong** — N=32, N=48 |

Decision after coarse pass: ⟨⟩

### sweep-n04

*(paste block)*

### sweep-n12

### sweep-n24

## 2.2 Refinement pass

Two points, chosen by 2.1.

### sweep-n⟨⟩

### sweep-n⟨⟩

## 2.3 `idle` · 24h floor window *(passive — schedule first, run alone)*

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
- [ ] NAT Gateway — per-GB processed (cross-check against E4)
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

## 2.4 Teardown · R5

After the final sweep point, **before** anything is destroyed. Fifteen minutes, and it is
what makes the retrieval-configuration study possible later without a cluster.

````bash
curl -X POST "http://localhost:6333/collections/${COLL}/snapshots"
curl -o corpus-v1.snapshot \
  "http://localhost:6333/collections/${COLL}/snapshots/${SNAPSHOT_NAME}"
aws s3 cp corpus-v1.snapshot s3://<bucket>/fixtures/qdrant/corpus-v1.snapshot
````

- [ ] Snapshot uploaded · checksum recorded: ⟨⟩
- [ ] `MANIFEST.md` alongside it: Qdrant version, embedding model + dimension, chunker
  image digest, `GET /collections/<name>` output, `corpus-profile.txt`
- [ ] One `kubectl top pod` reading of the Qdrant pod, for the §4.1 Block B instance
  class line: ⟨⟩
- [ ] Final `docs/report/data/` contents committed and pushed

---

# Part 3 · Close

## 3.1 Result matrix

Assembled from Part 2. Goes into `report.md` §3.1 verbatim.

| N | Config commit | Docs/min | Wall | Node-h spot | Node-h on-dem | $/run | $/1M docs | Saturation | Interrupts | Valid |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | | | | | |
| 12 | | | | | | | | | | |
| 24 | | | | | | | | | | |
| ⟨refine⟩ | | | | | | | | | | |
| ⟨refine⟩ | | | | | | | | | | |

Derived — all ᴬ:

| | Value | From |
| :--- | :--- | :--- |
| Knee | N=⟨⟩ | last point with a meaningful docs/min gain — threshold used: ⟨⟩ |
| Sweet spot | N=⟨⟩ | minimum `$/1M docs` |
| Waste boundary | N=⟨⟩ | `$/run` up substantially, throughput up under 10 % |
| Gap cost | ⟨⟩ | extra $/1M docs paid at the knee versus the sweet spot |
| Tier 1 constraint | ⟨⟩ | R4 at low N |
| Tier 2 constraint | ⟨⟩ | R4 after Tier 1 relieved — **only if E7/E9 landed and it was observed** |
| Warm-up share, lowest vs highest N | ⟨⟩ / ⟨⟩ | C6 |

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
| Query load run, Go API instrumentation | query path | Own frontier axis, own denominator — v2.0 |
| Retrieval configuration study (SQ recall, rescore, hybrid ablation, `hnsw_ef`) | — | Own axis; runs locally against the R5 snapshot, no cluster — v2.0 |
| Spot interruption injected under load | reliability economics | Needs its own run and instrumentation — v2.0 |
| Per-execution worker exit summaries | per-worker attribution | Counts from the frozen fixture, drain rate from E1, interruptions from `run-point.py` |
| Third constraint tier | §3.5 | Never claimed speculatively |
| Regression vs previous report | — | Unavailable at v1.0, no `Supersedes` |
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
- [ ] `architecture.md` p95 line relabelled as an unverified design target
- [ ] R5 snapshot uploaded and referenced from "Not covered"

## 3.4 Retro

- Which missing item cost the most time?
- Which run was wasted, and which gate should have caught it?
- Kit fixes to port back to `report-kit`:

**Article 2 positioning** — article 1 sold the architecture, article 2 sells the
economics. Do not make it technically deeper; make it about money. Sections most likely
to travel: the honest floor breakdown (§4.1), the knee/sweet-spot gap (§3.3), and the
Spot-versus-Fargate arithmetic (§4.4). The report may be 60 % complete and the article
still ships: priority order is §3.1 → §3.3 → §4.1 → §4.4, with §3.4 mandatory because it
is the *why* of the U-curve.
