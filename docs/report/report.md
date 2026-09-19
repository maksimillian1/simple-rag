# Executive Engineering Report — simple-rag

What asynchronous document ingestion costs, how many queries per second the deployment sustains,
and at what monthly volume the design pays for itself.

- **Report** — `simple-rag` · v1.0 · 2026-09-09
- **System under test** — chunker `sha-404a267` · indexer `sha-32365dc` · api `sha-bafdc1f` · tei `cpu-1.6` (tag, no digest pin) · commit `1ef1f0a8` · 2026-09-05 (the last cluster-identity capture before teardown; tags, not `sha256:` manifest digests, per `00-baseline`)
- **Envelope** — text-layer PDF corpus, bulk drop · N ≤ 125 · R ≤ 1000 req/s (untested above; no ceiling was found, and 1000 is not a swept maximum) · EKS + Karpenter Spot, KEDA autoscaling from 2 replicas, self-hosted Qdrant, TEI `bge-small-en-v1.5` · `eu-central-1`
- **Executions** — `00-baseline` · `01-ingestion` · `02-inference`
- **Cost source** — AWS Cost and Usage Report 2.0, hourly, resource IDs and split cost allocation on · `line_item_unblended_cost` · `eu-central-1` · USD
- **Raw data** — `executions/{00-baseline,01-ingestion,02-inference}/data/` · charts in `assets/` (none built yet: no `.svg`/`.csv` exists under `assets/`, and neither execution has `data/frontier.csv`, so the §3.2/§3.6 chart references point to no file)
- **Figures** — measured unless marked: ᴰ derived · ᴿ recorded · ᴱ estimated
- **Supersedes** — —
- **Changes** — first revision

The two paths have separate denominators: ingestion is priced per document, retrieval per query.
No table, chart or headline row in this report mixes them, and no conversion between the two is
published.

---

## Coverage

| Area | Status | Evidence | Cost of absence | Since |
| :--- | :--- | :--- | :--- | :--- |
| Ingestion throughput against concurrency | measured | §3.1 · `01-ingestion` | — | v1.0 |
| Ingestion cost per run | measured | §3.1 · `01-ingestion/M10` | — | v1.0 |
| Ingestion unit cost per 1M documents | derived ᴰ | §3.1 · `01-ingestion/D25` | — | v1.0 |
| Per-component share of ingestion cost | derived ᴰ | §4.2 · `01-ingestion/M12` | — | v1.0 |
| Embedding tier cost caused by ingestion | derived ᴰ | §4.2 · `01-ingestion/D23` | — | v1.0 |
| Warm-up and unused-capacity share | measured | §3.4 · `01-ingestion/D26` | — | v1.0 |
| Ingestion constraint ladder — Tier 1 | measured | §3.5 · `01-ingestion/M6` | — | v1.0 |
| Ingestion constraint ladder — Tier 2 | declared, not measured | §3.5, conditional on `01-ingestion` M15–M17 | which component becomes the ceiling once the chunker is relieved, and the price of the next step | v1.0 |
| Sustained query rate at the latency target | measured | §3.7 · `02-inference/D15` | — | v1.0 |
| Replica count required at that rate | measured | §3.6 · `02-inference/M7` | — | v1.0 |
| Query path constraint | measured | §3.7 · `02-inference/R14` | — | v1.0 |
| Retrieval cost per 1k queries — marginal | derived ᴰ | §4.2 · `02-inference/D16` | — | v1.0 |
| Generation cost per 1k queries — Bedrock | estimated ᴱ | §4.2 · `02-inference/E18` | — | v1.0 |
| Behaviour above the sustained rate | out of scope | — | whether the deployment degrades or collapses under overload. Latency past capacity measures the generator's backlog, so it needs served-rate and status-code instruments and its own runs | v1.1 |
| Scaler tuning — thresholds and cooldowns | declared, not measured | — | how much of the convergence time is configuration rather than node provisioning, and what a faster trigger would cost in replica churn | v1.1 |
| Idle floor, split A / B / C | measured over 1h (revised down from a planned 24h, because no cluster ever sat idle that long; `00-baseline` Preflight), extrapolated ᴰ | §4.1 · `00-baseline` §2 Floor | — | v1.0 |
| Allocation of untaggable billing lines | recorded ᴿ | §4.1 · `00-baseline/R5` | — | v1.0 |
| Amortization across volumes | derived ᴰ | §4.3 | — | v1.0 |
| Break-even against Fargate, ingestion | derived ᴰ | §4.4 · `01-ingestion/D29` | — | v1.0 |
| Ingest and query contention on shared Qdrant and TEI | declared, not measured | §3.8 · `02-inference` contention pass | whether the latency target survives a bulk ingest running underneath it, which is the state the system is actually in during a backfill | v1.0 |
| End-to-end latency including Bedrock generation | out of scope | — | the number a user experiences. It is bounded by an external quota, so it measures the provider rather than this configuration | — |
| Retrieval quality against quantization | declared, not measured | — | what INT8 compression costs in recall, and which retrieval configuration to run. INT8 SQ is a frozen given here, chosen for memory footprint | v1.1 |
| Reliability economics — Spot interruption injected under load | out of scope | — | the price of the resilience mechanism: work lost, duplicates, recovery time. Idempotency is designed in and verifiable by count comparison; pricing it needs its own run | — |
| Lambda as the build alternative | out of scope | — | a more dramatic §4.4. The cluster exists regardless, so the honest alternative is a different compute mode on the same platform | — |
| Reliability, levers and quality/cost sections | out of scope | — | template §6–§8 have no material at v1.0 and are absent rather than blank | — |
| Regression against a previous revision | out of scope | no predecessor | — | v1.1 |

---

## 1. BLUF

* **Ingestion cost at optimum** — $24,875<!--FD37--> / 1M docs ᴰ at N=25 (CUR actual, `01-ingestion` sweet spot). No Fargate comparison: D29 was declared and not made, because the rate card exists and the pod-hours don't (`01-ingestion` §3). Cost never bottoms mid-range. It rises monotonically with N, so "optimum" means the lowest clean N swept rather than a proven minimum, and the true floor may sit below N=25, untested
* **Sustained query rate** — ≥1000 req/s ᴿ at p95 = 2425ms once converged, on 6 API and 30 TEI replicas. The design target in `architecture.md` is p95 < 200ms. It is missed by ~2225ms, almost all of which is the frozen 2000ms Bedrock stub delay rather than system latency. No rate up to 1000 hit a ceiling
* **Retrieval cost** — $0.00375<!--FD65--> / 1k queries ᴰ marginal (CUR actual for the whole campaign, with the resting floor netted out once at campaign level; the per-point provisional `D16` figures understate it 1.5–4.3×, `02-inference` §3). On top of that: $0.000211<!--FD45--> ᴰ floor share at the sustained rate, a best case that assumes 1000 req/s continuously and grows far higher at realistic utilization (§4.3), and ~$0.51<!--FD39--> ᴱ for generation (1,800<!--FE1--> assumed input + up to 512<!--FR17--> output tokens × the real Bedrock rate). If generation is turned on, it would be ~136<!--FD115-->× the retrieval cost and dominate the total
* **Idle floor, Block B** — $553.83<!--FD26--> / month ᴰ (Block C total: $877.54<!--FD29--> ᴰ). This is what the feature costs with zero traffic on a platform that exists anyway
* **Primary constraints** — ingestion: none by resource signature; the limit is architectural. The sequential loop in `apps/indexer/src/main.py` keeps one TEI call in flight per pod, so throughput scales 1:1 with replica count rather than with CPU or memory · query: none found up to 1000 req/s. TEI's scale-out lags a rate step and then catches up, which is not a ceiling. Neither path has a price for the next scaling step, because neither hit a limit to relieve

**Verdict** — left to the business owner. Technical read: the system is cheap to run and has headroom on both paths at the volumes tested. Two gaps stand between this and a shippable verdict: no Fargate comparison for ingestion (D29, `docs/tech-debt.md` #10) and no measured cost for real Bedrock generation (E18, #9), which is the largest single number in the query-path cost and the one this report can least confirm. The contention pass is not a third gap but a declared scope boundary (Coverage): every query-path finding holds for an idle ingestion path only

---

## 2. Workload Contract & Envelope

### 2.1 Ingestion — per document

- **Unit of work** — one source document, complete when its last chunk is upserted and counted in Qdrant `points_count`
- **Workload fixture** — 100-file / 1.38GB stratified sample (~9.5% of the full corpus, 10 size deciles, seed 42), bulk drop · median 8.77MB, p95 49.23MB (page counts not captured; that would need opening all 100 PDFs) · frozen at commit `bafdc1f` (2026-08-31, the same freeze as the rest of the Plan, `00-baseline` §2)
- **Denominator** — 100 documents (files), frozen with the fixture. The same corpus is reloaded at every point, confirmed by an identical 84,018-chunk `points_count` (R21) six points running
- **Window** — opens at the first `s3:ObjectCreated`, closes when the ingestion pool reaches zero nodes and the embedding tier returns to its minimum, plus five minutes. Upload is outside the system under test

### 2.2 Query path — per query

- **Unit of work** — one search request, complete when the retrieved context is written to the response. Generation in Bedrock is outside the unit
- **Workload fixture** — 5 fixed query strings (`docs/report/scripts/load.js:57-63`), selected uniformly at random per request, replayed at a constant arrival rate against the collection produced by `01-ingestion`
- **Denominator** — queries served inside the steady-state window, produced by each run rather than frozen
- **Window** — designed to open once replicas and nodes had been stable for 60s and a further 60s of warm-up had elapsed. The actual `run-inference-point.py` preflight checks a single instant ("replicas == floor right now") with no duration requirement (`02-inference` §2). Closes when the generator stops

### 2.3 Conditions shared by both

- **Envelope** — `00-baseline` §2 Envelope
- **Metric sources** — `00-baseline` §1 · `01-ingestion/metrics.md` · `02-inference` §1
- **Autoscaling** — the Go API and the embedding tier scale from two replicas each under the triggers frozen in `00-baseline` §2. Every figure in this report is conditional on those triggers rather than on a replica count, and the ceilings were set out of reach so that no run measured them
- **Shared embedding tier** — one TEI deployment serves both paths. Ingestion runs raise its replica count, and that cost is charged to ingestion in §4.2 after the always-on minimum is subtracted
- **Worker packing density** — the ingestion pool is pinned to one instance type, giving ≈ 3–14 indexer pods per node (computed from frozen requests against `c7g.xlarge`/`2xlarge`/`4xlarge` allocatable, memory-bound; never observed live, `01-ingestion` §2). Denser packing amortises warm-up across more work and shifts the sweet spot in §3.3 to the right. Every ingestion figure is conditional on this ratio
- **Scalar quantization** — INT8 SQ is a fixed parameter, chosen for memory footprint. Its effect on retrieval quality is not measured and is not claimed either way

---

## 3. Efficiency Frontier

### 3.1 Ingestion — run matrix

Grid actually swept: 10, 25, 50, 75, 125, in place of the 4/12/24/refine/refine originally
planned (dropped once the trend proved monotonic; `01-ingestion` §1 Notes explains why). N=175,
the planned top, was never run; it was dropped once the cost trend proved monotonic downward
through N=25. N=10 is off-plan (added to reload Qdrant for `02-inference`) and non-standard
(fresh-cluster run, 2h12m wall time against 40-70min for the rest), but its real cost is trusted
(`01-ingestion` §3).

| N | Docs/min | Wall time | TEI peak | Compute $ | TEI $ | Other $ | $/run | $/1M docs | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 10 | 0.76 | 132.5 min | 3 | $1.55 | $0.31<!--FM25--> | $2.61 | $4.47<!--FD71--> ᴰ | **$44,707<!--FD76-->** ᴰ | none; chunker *also* at N ceiling (the only point below its ~20-concurrent corpus cap) |
| 25 | 1.62 | 61.7 min | 4 | $1.09 | $0.01<!--FM24--> | $1.38 | $2.49<!--FD70--> ᴰ | **$24,875<!--FD75-->** ᴰ (sweet spot) | none; indexer at ceiling, no resource pegged |
| 50 | 2.27 | 44.0 min | 10 | $1.26 | $0.29<!--FM23--> | $2.88 | $4.43<!--FD69--> ᴰ | $44,335<!--FD74--> ᴰ (knee) | none |
| 75 | 2.33 | 42.9 min | 16 | $1.54 | $0.52<!--FM22--> | $4.10 | $6.16<!--FD68--> ᴰ | $61,573<!--FD73--> ᴰ (waste boundary) | none; +39% cost for +2.6% docs/min over N=50 |
| 125 | 2.60 | 38.5 min | 26 | $2.01 | $0.82<!--FM21--> | $5.99 | $8.82<!--FD67--> ᴰ | $88,161<!--FD72--> ᴰ | none |

Excluded points: N=4/12/24 (never run, plan revised before the sweep started) and N=175 (planned
top, dropped once the trend proved monotonic downward through N=25). Config commits
and per-point validity decisions are audit trail and stay in `01-ingestion` §2.

Docs/min is measured twice from independent sources. Wall clock against the known corpus size
gives the point value; the derivative of queue depth gives the shape over time and catches a run
that stalled and recovered rather than draining steadily.

`$/run` is billed rather than computed. The cost and usage report carries hourly line items with
sub-hour usage amounts and resource identifiers, so a twenty-minute run inside one clock hour
resolves exactly, including the minutes a node was billed before its first pod started and
after its last one exited, which no cluster-side metric covers. Spot rows carry the price
actually charged in that hour, so no historical average is assumed anywhere in this report. Two
consequences shaped the campaign: runs are spaced one per clock hour, because two runs inside
one hour arrive as one summed row; and cost figures were read days after the runs, because the
report is delivered daily and revised until the month closes.

### 3.2 Ingestion — chart

`assets/frontier-ingestion.svg`, from `executions/01-ingestion/data/frontier.csv`. Dual Y axis,
X = N. Left: docs/min, rising then flat. Right: `$/1M docs`, falling to a minimum and rising
again.

### 3.3 Ingestion — knee · sweet spot · waste boundary

| Point | How it is identified | N | Evidence |
| :--- | :--- | :--- | :--- |
| Knee | last N where docs/min still rose meaningfully (threshold: 10% gain per step) | 50 | §3.1 |
| Sweet spot | lowest `$/1M docs` | 25 | §3.1 |
| Waste boundary | first N where `$/run` rises substantially for under 10 % throughput | 75: +39% cost for +2.6% docs/min over N=50 | §3.1 |

Running at the knee (N=50) instead of the sweet spot (N=25) costs $19,460<!--FD77--> extra per 1M docs
(Gap cost, `01-ingestion` §3) to buy +40% docs/min (1.62→2.27). The guardrail in §5 is set at the
sweet spot's observed concurrency (20 ᴱ: N=25's cap bound only at the peak, and the run held a
time-weighted mean of 19.5); the knee is the documented ceiling for a hurry.

The sweet spot (N=25) sits at the edge of the clean-cost range: no N below 25 has a trustworthy
cost read. N=10 exists but is off-plan and non-standard. Its real cost is higher than N=25's, so
it doesn't unseat N=25, and it doesn't confirm a true minimum either. No refinement pass placed a
clean point below N=25. `methodology.md` §7's caveat about this shape applies: the true minimum
may sit below 25, untested.

### 3.4 Shape of the ingestion cost curve

Every node is billed from provisioning but produces work only after boot, image pull and runtime
init. It is billed again for a tail after the last document, until consolidation removes it.
Both windows produce zero units at full price, and split cost allocation reports them directly:
capacity the bill charged for and no pod occupied.

**This mechanism was the original hypothesis, and it turned out not to dominate.**
`01-ingestion`'s finding (§3): `$/1M docs` rises monotonically with N across the whole tested
range, N=10 through 125, with no U-shape and no turn back up at high N distinct from a turn down
at low N. The constraint is architectural (§3.5: the indexer's sequential one-in-flight design)
rather than warm-up amortization. Every node does pay for boot and teardown around its real work;
that cost just isn't what drives the monotonic curve.

| N | Unused capacity $ ᴿ (fleet-wide) | Warm-up interval | Consolidation tail |
| :--- | :--- | :--- | :--- |
| 10 | $1.8478 | not captured; no per-point `M3`→`M4` node/pod timestamps were pulled | not captured |
| 25 | $1.4787 | not captured | not captured |
| 50 | $1.1984 | not captured | not captured |
| 75 | $1.4556 | not captured | not captured |
| 125 | $1.8123 | not captured | not captured |

Unused-capacity `$` (`M12`, pulled 2026-09-09, `01-ingestion` §3) is fleet-wide: it covers every
EKS node in the cluster that hour, not just `apps-compute`. There is no "share of compute $"
column, because it would mislead. `core-on-demand`'s and `database-on-demand`'s idle capacity
sits in every row regardless of ingestion load, so such a column can't separate the ingestion
pool's warm-up waste from platform-wide background idle. The shape (higher at N=10 and N=125,
lower in the middle) more plausibly tracks each point's wall-clock duration than N itself. N=10
ran 132.5min and N=125 ran 38.5min, and this is fleet-wide spend that accrues for as long as the
point's window lasts rather than a per-node effect.

### 3.5 Ingestion constraint ladder

* **Tier 1** — none, by resource signature. Proof: neither chunker nor indexer CPU or memory hit its frozen limit at any tested N (`01-ingestion/M6`). The ceiling is the indexer's architecture: the fully sequential `for msg in messages: process_sqs_message(...)` loop in `apps/indexer/src/main.py` holds exactly one in-flight TEI call per pod, so downstream concurrency is 1:1 with replica count regardless of CPU headroom. Cost to relieve: not measured. Relief means re-architecting the indexer for intra-pod parallelism; a resource bump won't do it.
* **Tier 2** — not measured. `01-ingestion/M15`–`M17` (TEI queue depth, TEI inference duration, Qdrant latency) never left "pending ServiceMonitor". The chunker was never relieved by a resource fix (Tier 1 isn't resource-shaped), so the precondition for naming a Tier 2 was never met.

Sweeping concurrency relieves tiers on its own: if chunker CPU is the ceiling at N=4, at N=24
there are six times as many chunkers and that ceiling is gone. Whatever saturates instead is a
proven second tier. This is why the sweep runs to 24 rather than stopping at 12.

If the embedding tier appears as Tier 2, its replica count decides what the finding means. A
tier still adding replicas when the queue grew was scaling too slowly; a converged tier at its
CPU limit was out of capacity. The two take different remedies and the report names which was
observed.

The hypothesis recorded before the first run: the ceiling was expected to be the Stage-1 chunker
rather than the embedding tier, because PyMuPDF extraction on a 300-page PDF is single-threaded
CPU work and may dominate embedding time by an order of magnitude, while the original design
assumed inference would saturate first. Outcome: **inverted.** The chunker held CPU headroom at
every tested N (peak ~20 concurrent regardless of N ∈ [50,125]); its ceiling never bound, and it
is set by the corpus rather than by resources. The constraint is the indexer's architecture
rather than a resource on either worker: one sequential in-flight TEI call per pod, so
throughput is capped by replica count rather than by CPU on any stage. Neither the predicted
component nor the predicted *kind* of ceiling (a capacity limit) held.

### 3.6 Query path — run matrix

The swept axis is arrival rate. Replicas are what the autoscaler produced, not a setting. Grid
actually run: 50, 200, 300, 500, 1000, in place of the 5/50/200/refine/refine originally planned.
r005 was never run. r300 was an off-plan point added after r500 to test whether 1000rps was worth
trying with more TEI headroom, not one of the two planned refinement points. p99 was never
queried: no guard references it, and `series.txt` has no `Q` ref for it.

| Offered req/s | Served req/s | api / tei replicas | Converge | p50 ms | p95 ms | p99 ms | Error % | $/1k queries ᴿ | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 50 | 45.5 (91%) | 2 / 3 | not timed, window avg already clean | 1672 | 2418 | — | 0% | $0.00250<!--FD78--> | none |
| 200 | 192.5 (96%) | 2 / 7 | not timed, window avg already clean | 1750 | 2425 | — | 0.24% avg / 4.0% peak | $0.00141<!--FD79--> | none |
| 300 | 296.4 (99%) | 3 / 11 | not timed, window avg already clean | 1749 | 2425 | — | 0.20% avg / 2.75% peak | $0.00098<!--FD80--> | none |
| 500 | 398.7 (80%, window avg) | 3 / 16 | ~7 min to 13 replicas, then clean | 2973 | 7934 (window avg) / **2425 once converged** | — | 0.78% avg (window) / **~0% once converged** | $0.00117<!--FD81--> | scale-out lag, not a ceiling |
| 1000 | 828.3 (83%, window avg) | 6 / 30 | ~4 min to 30 replicas, then clean | 2092 | 6378 (window avg) / **2425 once converged** | — | 4.97% avg (window) / **~0% once converged** | $0.00088<!--FD82--> | scale-out lag, not a ceiling |

Offered rate and served rate are reported separately. Where they diverge the generator, not the
system, was the limit, and the row is excluded from the capacity claim. r500's and r1000's window
averages look like a capacity collapse. Reading the time series directly shows a clean ramp to a
flat, zero-error steady state once TEI finished converging, which is a convergence-speed lag
rather than a ceiling (`02-inference` §3 Notes). The real campaign cost ($0.00375<!--FD65-->/1k queries,
CUR actual, `02-inference` §3) runs 1.5–4.3× higher than every `$/1k queries` figure in this table.
Those are per-point provisional reads that miss NAT entirely, along with the floor and settle
time between points. They are kept only to compare rates with each other, not as absolute costs.

The sweep climbs from below and stops at the target rather than pushing to a throughput ceiling.
Past capacity an open-loop generator queues its own excess, and the measured p95 then grows with
the length of the run instead of describing the system. What the system does above the sustained
rate is a coverage row, not a number here.

`assets/frontier-inference.svg`, from `executions/02-inference/data/frontier.csv`. X = offered
rate, left Y = p95 latency, right Y = replicas.

### 3.7 Query capacity and constraint

- **Sustained rate** — ≥1000 req/s, untested above that. Every rate up to 1000 reached the same steady-state p95 (~2425ms) and error floor (~0%) once TEI converged, so this is a lower bound rather than a proven ceiling
- **Capacity that rate required** — 6 API replicas and 30 embedding replicas at r1000, converged in ~4 min from the minimum of 2 each
- **Reference value** — the `p95 < 200 ms` line in `architecture.md`, a design target, **missed by ~2225ms** at every tested rate. Almost all of that is the frozen 2000ms Bedrock stub delay rather than retrieval latency. The retrieval-only path (subtracting the stub) would sit well inside 200ms, but that number was never isolated and measured directly
- **Constraint** — none found, by resource signature, up to 1000 req/s. Proof: `tei-embeddings` CPU runs high during scale-out (7.0-7.8 of 8 cores) and drops as replicas catch up, so it is not a sustained ceiling; `api` never exceeded 0.268 of its 0.5-core limit; Qdrant never exceeded 1.568 cores. With no ceiling found, there is nothing to relieve and no next scaling step to price

Retrieval is one gRPC round trip per query: dense, sparse and payload-text prefetch fused by
Qdrant with RRF, plus one embedding call. There is no cross-encoder and no GPU on the path, so
the ceiling is CPU on either the embedding tier or Qdrant rather than inference hardware.

The two are not equally relievable. The embedding tier scales horizontally, so a ceiling there
is priced in replicas. Qdrant runs on one dedicated node and does not, so a ceiling there is a
node-class decision and a larger change.

### 3.8 Contention — both paths on shared Qdrant and TEI

Qdrant serves ingestion writes and query reads from one node, and one embedding deployment
serves both paths, so a query-load run against an idle ingestion path measures a system nobody
runs during a backfill.

| Condition | Sustained req/s | p95 ms | api / tei replicas | Δ against §3.7 |
| :--- | :--- | :--- | :--- | :--- |
| query load only | ≥1000 (§3.7) | 2425 | 6 / 30 (at r1000) | — |
| query load with ingestion at the §5 guardrail | not run | not run | not run | not run |

Not attempted: the cluster was torn down before this pass was scheduled (`02-inference` §3
Close checklist). Declared, not measured, for v1.0 (Coverage table). Every §3.7 finding is
conditional on an idle ingestion path. Whether a concurrent backfill degrades the query path by
competing for the same TEI replicas, or whether the scaler simply adds more, is the largest open
item in this report.

---

## 4. Cost Structure

```
Monthly cost = Floor + ( Marginal_per_doc × Docs ) + ( Marginal_per_query × Queries )
                 ↑                  ↑                            ↑
               §4.1              §4.2                          §4.2
```

Every marginal figure below excludes floor lines by construction. The two serving deployments
never scale below two replicas each, so that permanently-on capacity is subtracted from every
run window before any per-unit number is computed.

### 4.1 Floor

Captured over a 1h idle window (revised down from a planned 24h) on a running, unloaded system, split rather than totalled.
Line-by-line audit: `00-baseline` §2 Floor. Every figure is a 1-hour measurement extrapolated
to a month ᴰ.

| Block | Line | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| **B · Dedicated** | Qdrant node + gp3 (current-gen PVC) · serving pool at 2+2 replicas · Bedrock interface endpoints · load balancer · S3 at rest · SQS polling | $553.83<!--FD26--> ᴰ | fixed (2 lines still variable/unrated: NAT transfer, Qdrant snapshots) |
| A · Shared | EKS control plane · core node group · Karpenter on Fargate ⚠ provisional · NAT hourly · monitoring stack (PVs still ᴰ) | $323.71<!--FD25--> ᴰ | fixed (2 lines still variable/unrated: NAT transfer, core transfer) |
| **C · Total** | `A + B` | $877.54<!--FD29--> ᴰ | — |

Right-sizing the same HA topology takes the fixed floor from $866.79<!--FD27--> ᴰ to
$753.26<!--FE10--> ᴱ/month, and the total from $877.54<!--FD29--> ᴰ to $764.02<!--FE11--> ᴱ
(`00-baseline` Right-sized floor · `docs/tech-debt.md` #5 and #12). The Block B half of that is
$457.30<!--FE9--> ᴱ, which is the number §5's budget alarm is set against — a floor the system
is not running at today, chosen deliberately so the alarm tracks the target rather than the
defect.

Block B is the headline: it is what leaves the bill if the feature is deleted. It is not divided
by an assumed number of co-tenant features: that divisor would be arbitrary, and blocks B and C
already answer both questions a reader can ask. Lines that carry no resource-level tag were
assigned to a block by hand and are marked ᴿ. They are 14.3% of the total (`R5`/`M2`,
`00-baseline`), which fails the 5% validity gate. The figure is kept anyway, because it is
dominated by AWS-managed lines that can't carry a custom tag rather than by gaps in this
project's tagging (`00-baseline` §2).

*The NAT gateway* is the hidden line of this architecture class and is missing from almost every
published version of it. It is billed hourly regardless of traffic, and again per gigabyte
processed, including image pulls and model weight downloads. The hourly charge is floor; the
per-gigabyte charge appears again in §4.2 as a marginal line.

*Interface VPC endpoints are the second hidden line.* Each is billed per hour per availability
zone, before a byte moves. Two of them exist only for this feature.

*Quantization sets the database instance class.* At 1M points × 384 dimensions, an INT8-quantized
resident copy needs 0.384 GB against 1.536 GB for float32 ᴰ, which is why the dedicated database
line is as small as it is. The measured Qdrant working set at teardown was 379 MiB (`qdrant-0`)
and 97.7 MiB (`qdrant-1`) ᴿ. The ~4x asymmetry between two replicas of the same collection is
unexplained and was not chased this pass. Either reading is an upper bound rather than a matching
figure, because it includes page cache on memory-mapped segments. The
retrieval cost of that compression is not measured here.

*The query path is why the serving line exists.* Both deployments hold two replicas at zero
traffic, because a request arriving at zero replicas pays a cold start. §3.7 states what that
permanently-on capacity buys in requests per second before the autoscaler has to act.

*Article 1 advertised "$0.00 on idle."* This table shows how many lines that holds for: 3 of 17
Floor lines are ~$0 at idle (Qdrant snapshot storage, S3, SQS), and every compute, node-group and
endpoint line is nonzero spend. The claim was about the elastic ingestion tier but reads as if it
covers the whole system, so both numbers are stated here.

### 4.2 Marginal

Floor lines are excluded by definition. At the sweet spot (N=25, `01-ingestion/M12`, pulled
2026-09-09), 4 components come from one clean, non-overlapping source (`split_line_item_split_cost`
per pod) and sum correctly. The rest of the $24,875<!--FD37--> total does not decompose further with the
data available, so it is stated as a gap instead of being forced into rows that would not add up.

**Per 1M documents ingested, at N=25 (the sweet spot)**

| Component | $/1M docs | Share |
| :--- | :--- | :--- |
| Stage-1 chunker pods | $21<!--FM42--> | 0.1<!--FD111-->% |
| Stage-2 indexer pods | $2,574<!--FM43--> | 10.3<!--FD112-->% |
| Embedding tier above its always-on minimum | $2,490<!--FD109--> ᴰ ($3,256<!--FM44--> total apportioned − $766<!--FM45--> idle-floor share for this window) | 10.0<!--FD113-->% |
| NAT, SQS, S3, and node capacity billed to no pod, combined | $19,790<!--FD110--> ᴰ (not decomposable further: `M12`'s `unused_cost` is fleet-wide rather than isolated to `apps-compute`, and it doesn't reconcile cleanly against the Matrix's NAT+baseline "Other $" figure, so a further split here would look precise without being so) | 79.6<!--FD114-->% |
| **Total** | $24,875<!--FD37--> ᴰ | 100% |

The boundary between the pod rows is drawn by the cloud provider, not measured at either pod.
Only the instance is billed; splitting that one charge across the pods on it uses their requests
and usage against a fixed CPU-to-memory weighting. The total is exact and the internal split is
a convention. That is why §3.4 argues from the unoccupied-capacity row, which needs no
convention.

**Per 1k queries served, at the sustained rate**

| Component | $/1k queries | Share |
| :--- | :--- | :--- |
| Serving capacity above the always-on minimum | $0.00375<!--FD65--> ᴰ (campaign CUR actual, floor netted once; caveat after this table) | 100% |
| **Marginal total** | $0.00375<!--FD65--> ᴰ | 100% |
| Floor share at the sustained rate | $0.000211<!--FD45--> ᴰ (best case; negligible only because 1000 req/s continuously is a huge volume) | — |
| Bedrock generation, at ~1,800<!--FE1--> input and up to 512<!--FR17--> output tokens | ~$0.51<!--FD39--> ᴱ | — |

The three lines answer different questions and are not summed into a headline. The marginal
total is what an additional query costs once the tier is already scaled. It uses the campaign
CUR read (`02-inference` §3), not the per-point provisional `D16` figures in §3.6, which
understate it 1.5–4.3× because they miss NAT entirely and the floor and settle time between points.
The floor share assumes the tier runs at the sustained rate (1000 req/s) continuously, which
makes it an extreme best case: it is negligible only because 1000 req/s continuously serves
2,628,000,000<!--FD116--> queries/month. At every volume in the §4.3 table the floor dominates
instead; the crossover there is ~148M queries/month, far above anything swept. The generation line is a vendor
rate applied to a token count nobody swept, derived from the real prompt template
(`apps/api/core/llm.go`, `02-inference/E18`). No run called the provider. **If generation is
turned on, it would be ~136<!--FD115-->× the marginal retrieval cost**, the largest line in the
query-path cost and the one this report can least confirm.

### 4.3 Amortization

`Effective $/unit = ( Block B + Marginal × V ) ÷ V`. Arithmetic on §4.1 and §4.2, no run. Block
B is the right floor: for a feature on a cluster that exists anyway, the question is what this
feature costs to keep alive, not what the platform costs.

**Each table below charges the whole of Block B.** They are two readings of the same floor under
two different denominators, and they are not addends: adding a `$/doc` row to a `$/query` row
counts the same monthly floor twice. The conversion that would make them additive needs an
arrival ratio nobody measured.

Uses Block B = $553.83<!--FD26-->/month and the sweet-spot marginal rate, $24,875<!--FD37-->/1M docs = $0.02488<!--FD38-->/doc.

| Monthly documents | Effective $/doc ᴰ | Floor share |
| :--- | :--- | :--- |
| 1 000 | $0.5787<!--FD92--> | 95.7<!--FD96-->% |
| 10 000 | $0.0803<!--FD93--> | 69.0<!--FD97-->% |
| 100 000 | $0.0304<!--FD94--> | 18.2<!--FD98-->% |
| 1 000 000 | $0.0254<!--FD95--> | 2.2<!--FD99-->% |

Uses Block B = $553.83<!--FD26-->/month and the real campaign marginal rate, $0.00375<!--FD65-->/1k queries = $0.00000375<!--FD100-->/query.

| Monthly queries | Effective $/query ᴰ | Floor share |
| :--- | :--- | :--- |
| 10 000 | $0.05539<!--FD101--> | 99.99<!--FD105-->% |
| 100 000 | $0.00554<!--FD102--> | 99.93<!--FD106-->% |
| 1 000 000 | $0.00056<!--FD103--> | 99.3<!--FD107-->% |
| 10 000 000 | $0.0000591<!--FD104--> | 93.7<!--FD108-->% |

Below ~22,265<!--FD41--> documents and ~147,819,238<!--FD43--> queries per month, the volumes where floor share drops
under half, you pay mostly for the feature to exist rather than for work done. Those two volumes
are the lower bound of where this design makes economic sense. The asymmetry is not a rounding
artifact. Ingestion crosses 50% floor share at a modest volume because its marginal cost per unit
is comparatively large. The query path's marginal cost per unit is three orders of magnitude
smaller, so the floor dominates it at every volume in the query table: even 10M queries/month
sits at 93.7<!--FD108-->% floor share, nowhere near the crossover.

### 4.4 Break-even against Fargate, ingestion only

The cluster exists regardless, so the relevant alternative is a different compute mode for the
same ingestion Jobs. Fargate removes node provisioning, per-node image pull
and Spot interruption handling, and charges per vCPU-second and GB-second at a premium over EC2
Spot. The comparison is direct because §3.1 already measured what a run consumes. The embedding
tier is outside it: a shared serving deployment either way.

**Not computed: `01-ingestion/D29` was declared and not made.** The rates exist
(`eu-central-1` Fargate pricing in `00-baseline/data/price-2026-09-09.json`, pulled from the AWS
Price List API on 2026-09-09: $0.04656<!--FR5-->/vCPU-hour, $0.00511<!--FR6-->/GB-hour). The pod-hours don't. `M12`'s
per-workload split gives dollars rather than raw CPU and memory pod-hours, and the Matrix's
`N reached` column is the indexer's time-weighted concurrency only. The chunker's concurrency,
described only as "headroom" peaking at ~20 regardless of N, was never captured as a
time-weighted mean. Filling this table would mean guessing the chunker's average concurrency at
every N, so it stays empty.

| | Karpenter Spot (measured) | Fargate ᴰ |
| :--- | :--- | :--- |
| vCPU-hours per 1M docs | not computed | same workload, same figure |
| GB-hours per 1M docs | not computed | same workload, same figure |
| Unoccupied capacity paid (§3.4) | not decomposable (§4.2) | per-task cold start, no per-node image pull |
| Effective $/1M docs | $24,875<!--FD37--> ᴰ (sweet spot, N=25) | not computed |
| Interruption handling required | yes, the SIGTERM path in the workers | no |
| Feature floor impact | 0 at idle | 0 at idle |

The Fargate column is a lower bound on what Fargate would cost. No Spot capacity type exists for
it on EKS, so the comparison runs against On-Demand rates; requests are billed at the next step
of a fixed vCPU and memory grid; and each task gets its own microVM, so image pull is paid per
worker rather than amortised across a node. All three move the column up.

**Crossover** — not computed, for the same reason: there is no Fargate-side cost to compare against.

The query path has no Fargate variant to compare against: two replicas of each deployment are
persistent by design, and per-second billing buys nothing when the pod never stops.

---

### 4.5 Bedrock VPC endpoint, query path

The alternative to PrivateLink is the NAT gateway §4.1 already pays for. At a reference
1,000,000<!--FE14--> queries per month, `02-inference/E18`'s 2,312<!--FD117--> tokens per query
weigh 8.6<!--FD52--> GB:

| | Via NAT | Via the endpoint |
| :--- | ---: | ---: |
| Network | $0.45<!--FD53--> ᴱ | $26.28<!--FD48--> ᴰ + pending ᴱ |
| Generation | $508.64<!--FD51--> ᴱ | $508.64<!--FD51--> ᴱ |
| Network as a share of generation | **0.09<!--FD55-->%** ᴱ | — |

Transport is not a cost argument on this path (`02-inference/K4`). `ADR-0007` rests the endpoint
on a privacy boundary and on "slashes NAT Gateway data processing charges": the first holds, the
second does not. The crossover (`02-inference/D22`) reads `pending` until the PrivateLink rate is
pulled; across the values its inputs allow it falls between 31.5M and 72.6M queries per month.

Reading the deployment settles two defects without a run, both `docs/tech-debt.md` #12: the
`bedrock` control-plane endpoint, $26.28<!--FD47-->/month of `block_b_fixed`, is reachable by nothing, and
the runtime endpoint's private DNS never matches the hostname the client resolves.

---

## 5. Guardrails

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Ingestion concurrency ceiling | recommend `maxReplicaCount: 20` ᴱ — the sweet-spot run (N=25) held a time-weighted mean of 19.5, so its cap bound only at the peak. No point separates 20 from 25, so this is not a claim that 20 is cheaper, and it holds for this corpus only (the chunker's ~20-concurrent ceiling is corpus-driven). **Live value raised 10 → 20** to match, 2026-09-19, on both ScaledJobs; it applies at the next cluster bootstrap | §3.3 sweet spot · `01-ingestion` Guardrails | `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml` |
| Chunker memory limit | not revised. The live `limits.memory: 1Gi` already sits at ~2.3x the 433Mi peak observed (`n50-test` sample), well past the `peak+30%` (563Mi) this formula would suggest, and nothing argues for moving it either way | `01-ingestion/M7`, valid only where `M8` is zero | `deploy/k8s/apps/chunker` |
| Indexer memory limit | not revised. `01-ingestion/M7`'s per-point peak memory isn't in this report at the precision needed, and `M8` (OOMKilled) never returned a confirmed zero (recurring GC-race gap), so ingestion data alone doesn't support a revision | `01-ingestion/M7`, valid only where `M8` is zero | `deploy/k8s/apps/indexer` |
| Node consolidation delay | not revised; live `apps-compute: 30s` unchanged. §3.4's unoccupied-capacity number is fleet-wide and too coarse to argue for a different value | §3.4 unoccupied-capacity share | `apps-compute` NodePool |
| Max input file size | `MAX_ALLOWED_SIZE_BYTES: 104857600` (100MB, code default, unchanged). The sample corpus's p95 (49.23MB) sits well under it, but the full corpus has an untested file of up to 124MB, above it | §3.5 · ADR-0001 | `apps/chunker` env |
| Chunks per SQS message | `BATCH_SIZE: 30` (code default, unchanged) | §4.2 SQS line · ADR-0004 | `apps/chunker` env |
| Go API replica ceiling | live `maxReplicaCount: 10`. 6 replicas were observed at r1000 (D15's lower bound), so some margin exists, but D15 is untested above 1000 req/s and the setting isn't confirmed sufficient at a higher rate | §3.7 replicas at the sustained rate, plus margin | `api-scaler` |
| Embedding tier replica ceiling | keep live `maxReplicaCount: 30`. It was **fully used at r1000 with zero margin**, and it carried that rate: 30 replicas sustained ≥1000 req/s at the steady-state p95 and ~0% error (§3.7), which is the rate this deployment is sized for. No quota increase is requested. Above 1000 req/s the cap binds first, then this account's Spot vCPU quota (`L-34B43A08`=256), which allows a realistic ~35-40 replicas at the 6-core request | §3.7 replicas at the sustained rate | `tei-embeddings-scaler` |
| Go API memory limit | not revised; no OOM or working-set warning surfaced in any point's Notes across the sweep | `02-inference/M6` | `deploy/k8s/apps/api` |
| Embedding tier memory limit | not revised, for the same reason; CPU, not memory, was the driver at every rate | `02-inference/M6` | `deploy/k8s/apps/tei` |
| Query rate alert | not set. `D15` is a lower bound (≥1000, untested above), so `D15 × 0.8` would alert on a number already known to be too low | §3.7 | `prometheus/rules.yaml` |
| Latency SLO alert | not set. Every p95 in this campaign is dominated by the fixed 2000ms mock delay, and a threshold tuned against it wouldn't transfer to real Bedrock traffic without at least one real-generation calibration point, which this report never took | §3.7 | `prometheus/rules.yaml` |
| Backfill concurrency during query hours | not set; the contention pass never ran (§3.8), so there is nothing to base it on | §3.8 | `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml` |
| Ingestion backlog alert | not set; `01-ingestion` never defined a drain-rate alert formula distinct from the point-close criterion already in use | §3.1 | `prometheus/rules.yaml` |
| Budget alarm | recommend $640.22<!--FD56--> ᴱ/month (right-sized Block B × 1.4 = $457.30<!--FE9--> × 1.4). Set against the right-sized floor rather than the as-built one, so the alarm tracks the target the tech-debt items move toward instead of pinning today's defects in place. **`terraform/budgets.tf` does not exist**, so nothing enforces this today (`docs/tech-debt.md` #11) | §4.1 | `terraform/budgets.tf` (not yet created) |
