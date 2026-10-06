# Executive Engineering Report — simple-rag

What asynchronous document ingestion costs, how many queries per second the deployment sustains,
and at what monthly volume the design pays for itself.

- **Report** — `simple-rag` · v1.0 · 2026-09-09
- **System under test** — chunker `sha-404a267` · indexer `sha-32365dc` · api `sha-bafdc1f` · tei `cpu-1.6` (tag, no digest pin) · commit `1ef1f0a8` · 2026-09-05 (the last cluster-identity capture before teardown; tags, not `sha256:` manifest digests, per `00-baseline`). That commit carries TEI at 6 cores / 8 limit, which only `inference-r1000` ran on; every other point, and the whole floor, ran `cfa0ab79` at 3 / 4 (`docs/tech-debt.md` #4)
- **Envelope** — text-layer PDF corpus, bulk drop · N ≤ 125 · R ≤ 1000 req/s\* (untested above; no ceiling was found, and 1000 is not a swept maximum) · EKS + Karpenter Spot, KEDA autoscaling from 2 replicas, self-hosted Qdrant, TEI `bge-small-en-v1.5` · `eu-central-1`
- **Executions** — `00-baseline` · `01-ingestion` · `02-inference`
- **Cost source** — `docs/report/methodology.md` §9 "Cost calculation approach (AWS)", basis in `00-baseline` §2 · AWS Cost and Usage Report 2.0 · `eu-central-1` · USD
- **Raw data** — `executions/{00-baseline,01-ingestion,02-inference}/data/`
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
| Embedding tier cost caused by ingestion | measured, two readings | cash: §3.1 `TEI $` · `01-ingestion/D23` · apportioned: §4.2 · `01-ingestion/M12` | — | v1.0 |
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
| Idle floor, split A / B / C | one resting hour's inventory × published unit rate × 730 ᴰ (`docs/report/methodology.md` §9). The hour was revised down from a planned 24 h because no cluster ever sat idle that long (`00-baseline` Preflight), so the projection carries that hour's prices, Spot included | §4.1 · `00-baseline` §2 Floor | — | v1.0 |
| Errors found at rest, excluded from the floor | measured, itemised, not amortised ᴰ | `00-baseline` §2 Floor errors table | $175.85<!--FD35-->/month recurring and $78.31<!--FD36--> already spent sit outside every Floor figure here, being defects rather than sizing. The one exception is the `bedrock` control-plane endpoint, which was provisioned and billed and so stays inside the as-built floor (`docs/tech-debt.md` #12) | v1.0 |
| Untaggable billing lines, mapped to the Floor rows that price them | recorded ᴿ | §4.1 · `00-baseline/R5` | — | v1.0 |
| Amortization across volumes | derived ᴰ | §4.3 | — | v1.0 |
| Break-even against Fargate, ingestion | derived ᴰ | §4.4 · `01-ingestion/D29` | — | v1.0 |
| Ingest and query contention on shared Qdrant and TEI | declared, not measured | §3.8 · `02-inference` contention pass | whether the latency target survives a bulk ingest running underneath it, which is the state the system is actually in during a backfill | v1.0 |
| End-to-end latency including Bedrock generation | out of scope | — | the number a user experiences. It is bounded by an external quota, so it measures the provider rather than this configuration | — |
| Wire weight of a query, headers and framing included | declared, not measured | §4.4 · `02-inference/K4` | every byte figure on the query path rests on three estimates whose biases run in opposite directions, so the VPC endpoint crossover is an order of magnitude and not a threshold. One run that actually calls Bedrock replaces all three at once, from `EUC1-NatGateway-Bytes` over its own window (`docs/tech-debt.md` #9) | v1.0 |
| Retrieval quality against quantization | declared, not measured | — | what INT8 compression costs in recall, and which retrieval configuration to run. INT8 SQ is a frozen given here, chosen for memory footprint | v1.1 |
| Reliability economics — Spot interruption injected under load | out of scope | — | the price of the resilience mechanism: work lost, duplicates, recovery time. Idempotency is designed in and verifiable by count comparison; pricing it needs its own run | — |
| Lambda as the build alternative | out of scope | — | a more dramatic §4.4. The cluster exists regardless, so the honest alternative is a different compute mode on the same platform | — |
| Reliability, levers and quality/cost sections | out of scope | — | template §6–§8 have no material at v1.0 and are absent rather than blank | — |
| Regression against a previous revision | out of scope | no predecessor | — | v1.1 |

---

## 1. BLUF

* **Ingestion cost at optimum** — $24,875<!--FD37--> / 1M docs ᴰ at N=25 (CUR actual, `01-ingestion` sweet spot). Fargate for the same two workers costs 2.91<!--FD123-->× more at that point (D29, §4.4), computed at N=25 only. Cost rises monotonically from N=25 upward; N=10, the only point below it, is higher still ($44,707<!--FD76--> ᴰ), so N=25 is a measured local minimum rather than a boundary guess
* **Sustained query rate** — 1000 req/s\*, held for 1m45s. From 14:57:16 to 14:59:01Z, with `tei-embeddings` at 30 replicas, the fleet served 998<!--FM60-->–1,001<!--FM61--> req/s at a flat p95 of 2425ms and 0.02<!--FM62-->% errors. Then the generator stalled — k6 silent from 08m30s to 11m28s elapsed, completions down to 43/s, the embedding tier scaling in 30 → 6 for want of traffic — and the second ramp carried this point's worst latency and errors. Over the full steady phase the point served 955<!--FM63--> req/s at 0.28<!--FM64-->% errors, against `D15`'s 0.1<!--FR29-->% bound: not met. The design target in `architecture.md` is p95 < 200ms, which the frozen 2000ms Bedrock stub puts out of reach by construction; read from the generator's own per-request durations instead, retrieval plus the internet round trip is ~40-60ms (§3.7)
* **Retrieval cost** — $0.00375<!--FD65--> / 1k queries ᴰ marginal (CUR actual for the whole campaign, with the resting floor netted out once at campaign level; the per-point provisional `D16` figures understate it 1.5–4.3×, `02-inference` §3). On top of that: $0.000203<!--FD45--> ᴰ floor share at the sustained rate, a best case that assumes 1000 req/s continuously and grows far higher at realistic utilization (§4.3), and ~$0.51<!--FD39--> ᴱ for generation (1,800<!--FE1--> assumed input + up to 512<!--FR17--> output tokens × the real Bedrock rate). If generation is turned on, it would be ~136<!--FD115-->× the retrieval cost and dominate the total
* **Idle floor, Block B** — $534.12<!--FD26--> / month ᴰ (Block C total: $877.54<!--FD29--> ᴰ). This is what the feature costs with zero traffic on a platform that exists anyway

\* **1000 req/s** means the 1m45s hold above, not the r1000 window and not a proven ceiling.
Every later use of the figure carries the asterisk back to this qualification and to §3.7.

**What the sweep settled**

* **Ingestion is capped by code, not by hardware.** Nothing saturated at any N. Throughput scales
  with replica count because the sequential loop in `apps/indexer/src/main.py` holds one TEI call in
  flight per pod, so 26 embedding replicas were needed to reach 2.60 docs/min at N=125, and docs/min
  was still climbing when the sweep stopped on cost rather than on a ceiling. Sizing cannot move
  this line. The loop can.
* **On the query path the component closest to a hard ceiling is the one that cannot scale.** TEI
  touched 97.5% of its CPU limit during r1000's ramp, which more replicas relieved and did. Qdrant
  reached 1.568<!--FM59--> of its 2<!--FR27-->-core limit, 78<!--FD137-->%, and has nowhere to go:
  two replicas hold one shard at every rate. What the path costs follows arrival rate, not volume.
  Below ~54<!--FD143--> requests a second the bill is the floor; above it the floor falls to
  22.2<!--FD141-->% at 500M queries a month and 12.5<!--FD142-->% at a billion, and everything paid
  for beyond it is an embedding replica, since `api` holds two until ~300 req/s.
* **The defects cost more than the sizing.** Errors found at rest recur at $175.85<!--FD35-->/month
  against $139.80<!--FD138--> ᴱ saved by right-sizing every line in the floor — and $52.56 of that
  saving is the two Bedrock endpoints, which the errors table counts as a defect rather than a
  size, so sizing alone accounts for $87.24<!--FD152--> ᴱ. Looking for what should not be running paid better
  than sizing what should.
* **The two paths want opposite operating points.** Cost per document rises with concurrency:
  $24,875<!--FD37--> ᴰ per 1M docs at the N=25 optimum against $88,161<!--FD72--> ᴰ at N=125. Cost
  per query falls with rate: $0.00250<!--FD78--> ᴰ per 1k at 50 req/s against $0.00088<!--FD82--> ᴰ
  at 1000. Ingestion is cheapest run slowly, the query path is cheapest run hot, and they share no
  operating point, so spare capacity in one is not an argument for scheduling the other into it.

**Verdict** — **ship with guardrails.** The system is cheap to run at the volumes tested and has
headroom on both paths, and nothing found here blocks release. The guardrails are §5's committable
values, and three of them are conditions rather than suggestions: `single_nat_gateway = false` in
production (`ADR-0017`), the budget alarm at $575.84<!--FD56--> ᴱ/month, and the ingestion
concurrency ceiling at 20 ᴱ. What ships with a declared gap is the generation cost: `E18` at
~$0.51<!--FD39--> ᴱ/1k queries is an estimate, no run has called Bedrock, and it is
136<!--FD115--> ᴱ times the measured retrieval cost, so the largest number in the query path is
the one this report can least confirm (`docs/tech-debt.md` #9). The Fargate comparison is made at
the N=25 sweet spot only; the other four points need the same integration of `M5` (#10). The
contention pass is a declared scope boundary (Coverage) and not a gap: every query-path finding
holds for an idle ingestion path only.

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
- **Autoscaling** — the Go API and the embedding tier scale from two replicas each under the triggers frozen in `00-baseline` §2. Every figure in this report is conditional on those triggers rather than on a replica count. The ingestion ceilings stayed out of reach, so no ingestion run measured one; the embedding tier reached its `maxReplicaCount: 30` at r1000. `02-inference`'s validity rule excludes a point that sits at its ceiling, and this one is kept as the declared exception: the tier converged there and held the offered rate at the steady-state p95 with ~0% errors (§3.7), so 30 is a count that sufficed rather than a limit that bound
- **Shared embedding tier** — one TEI deployment serves both paths. Ingestion runs raise its replica count, and that cost is charged to ingestion in §4.2 after the always-on minimum is subtracted
- **Worker packing density** — the ingestion pool is pinned to one instance type, giving ≈ 3–14 indexer pods per node (computed from frozen requests against `c7g.xlarge`/`2xlarge`/`4xlarge` allocatable, memory-bound; never observed live, `01-ingestion` §2). Denser packing amortises warm-up across more work and shifts the sweet spot in §3.3 to the right. Every ingestion figure is conditional on this ratio
- **Scalar quantization** — INT8 SQ is a fixed parameter, chosen for memory footprint. Its effect on retrieval quality is not measured and is not claimed either way

---

## 3. Efficiency Frontier

### 3.1 Ingestion — run matrix

**N is the `maxReplicaCount` set on both ScaledJobs for that run** — the chunker's and the
indexer's — edited in the manifests before the point opened and recorded by
`run-ingestion-point.py --n`, which reports it rather than setting it. It is a cap on concurrent
pods, not an observed concurrency: the indexer tracked it exactly at every point (`M5` 125/125 at
N=125), while the chunker peaked at ~20 regardless of N because the 100-file corpus cannot keep
more busy. The cap bound on the chunker only at N=10, where 10 is stricter than that ~20. Between
runs the committed value was 10, raised to 20 on 2026-09-19 to match the observed ceiling (D6,
§5); no run was made at that value.

Grid actually swept: 10, 25, 50, 75, 125, in place of the 4/12/24/refine/refine originally
planned (`01-ingestion` §1 Notes explains why). N=10 is off-plan (added to reload Qdrant for
`02-inference`) and non-standard (fresh-cluster run, 2h12m wall time against 40-70min for the
rest), but its real cost is trusted (`01-ingestion` §3).

| N | Docs/min | Wall time | TEI peak | Compute $ | TEI $ | Other $ | $/run | $/1M docs | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 10 | 0.76 | 132.5 min | 3 | $1.55 | $0.31<!--FM25--> | $2.61 | $4.47<!--FD71--> ᴰ | **$44,707<!--FD76-->** ᴰ | none; chunker *also* at N ceiling (the only point below its ~20-concurrent corpus cap) |
| 25 | 1.62 | 61.7 min | 4 | $1.09 | $0.01<!--FM24--> | $1.38 | $2.49<!--FD70--> ᴰ | **$24,875<!--FD75-->** ᴰ (sweet spot) | none; indexer at ceiling, no resource pegged |
| 50 | 2.27 | 44.0 min | 10 | $1.26 | $0.29<!--FM23--> | $2.88 | $4.43<!--FD69--> ᴰ | $44,335<!--FD74--> ᴰ (knee) | none |
| 75 | 2.33 | 42.9 min | 16 | $1.54 | $0.52<!--FM22--> | $4.10 | $6.16<!--FD68--> ᴰ | $61,573<!--FD73--> ᴰ (waste boundary) | none; +39% cost for +2.6% docs/min over N=50 |
| 125 | 2.60 | 38.5 min | 26 | $2.01 | $0.82<!--FM21--> | $5.99 | $8.82<!--FD67--> ᴰ | $88,161<!--FD72--> ᴰ | none |

Excluded points: N=4/12/24 (never run, plan revised before the sweep started) and N=175 (planned
top, never run; dropped once the trend proved monotonic downward through N=25). Config commits
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

### 3.2 Ingestion — frontier

§3.1's Matrix is the frontier: docs/min against N, which rises monotonically and never flattens,
and `$/1M docs` against N, which rises monotonically from N=25 upward rather than dipping to a
minimum somewhere in the middle. A frontier is expected to bend; this one does not, and §3.3 names
what stands in for the knee.

### 3.3 Ingestion — knee · sweet spot · waste boundary

| Point | How it is identified | N | Evidence |
| :--- | :--- | :--- | :--- |
| Knee | **not identified.** The stated rule — last N whose step still gained 10% docs/min — selects 125, the top of the swept range, because the per-step gains are not monotone: +113%, +40%, +2.6%, then +11.6% again. A rule that lands on the edge of the range has found no bend | — | §3.1 |
| Sweet spot | lowest `$/1M docs` | 25 | §3.1 |
| Waste boundary | first N where `$/run` rises substantially for under 10 % throughput | 75: +39% cost for +2.6% docs/min over N=50 | §3.1 |

Running at N=50 instead of the sweet spot (N=25) costs $19,460<!--FD77--> extra per 1M docs
(Gap cost, `01-ingestion` §3) to buy +40% docs/min (1.62→2.27). N=50 is the documented ceiling for
a hurry — the last step before gains first stalled, which is not the same thing as a knee, since
the step after it gained again. The guardrail in §5 is set at the sweet spot's observed
concurrency (20 ᴱ: N=25's cap bound only at the peak, and the run held a time-weighted mean of
19.5).

N=25 is a measured local minimum, not a boundary artefact. The one point below it, N=10, is
off-plan and non-standard (fresh cluster, 2h12m against 40-70min) but its cost read is a genuine
one, and it is higher: $44,707<!--FD76--> ᴰ against $24,875<!--FD75--> ᴰ, which low throughput
holding the fixed per-hour costs open for twice as long accounts for. So the curve descends into
N=25 and climbs out of it on both sides of the swept range. What stays untested is the gap between
10 and 25, where no point was placed.

### 3.4 Shape of the ingestion cost curve

Every node is billed from provisioning but produces work only after boot, image pull and runtime
init. It is billed again for a tail after the last document, until consolidation removes it.
Both windows produce zero units at full price, and split cost allocation reports them directly:
capacity the bill charged for and no pod occupied.

This mechanism was the original hypothesis, and it did not dominate.
`01-ingestion`'s finding (§3): `$/1M docs` rises monotonically from N=25 up to N=125, and N=10 —
the only point below the minimum — is higher still, so the curve is a V with its floor at the
second-lowest N swept rather than a warm-up bowl with a turn at each end. The constraint is
architectural (§3.5: the indexer's sequential one-in-flight design)
rather than warm-up amortization. Every node does pay for boot and teardown around its real work;
that cost just isn't what drives the monotonic curve.

| N | Unused capacity $ ᴿ (fleet-wide) | Warm-up interval | Consolidation tail |
| :--- | :--- | :--- | :--- |
| 10 | $1.8478<!--FM72--> | not captured; no per-point `M3`→`M4` node/pod timestamps were pulled | not captured |
| 25 | $1.4787 | not captured | not captured |
| 50 | $1.1984<!--FM73--> | not captured | not captured |
| 75 | $1.4556<!--FM74--> | not captured | not captured |
| 125 | $1.8122<!--FM75--> | not captured | not captured |

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
assumed inference would saturate first. Outcome: the hypothesis was inverted. The chunker held CPU headroom at
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
queried.

| Offered req/s | Served req/s | api / tei replicas | Converge | p50 ms ᴿ | p95 ms ᴿ (Envoy) | p95 ms (k6) | Error % | $/1k queries (gross) ᴰ | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 50 | 45.5 (91%) | 2 / 3 | not timed, window avg already clean | 1672 | 2418 | **2040** | 0% | $0.00250<!--FD78--> | none |
| 200 | 192.5 (96%) | 2 / 7 | not timed, window avg already clean | 1750 | 2425 | **2150** | 0.24% avg / 4.0% peak | $0.00141<!--FD79--> | none |
| 300 | 296.4 (99%) | 3 / 11 | not timed, window avg already clean | 1749 | 2425 | **2060** | 0.20% avg / 2.75% peak | $0.00098<!--FD80--> | none |
| 500 | 398.7 (80%, window avg) · **499<!--FM66-->–501<!--FM67--> held 1 min** | 3 / 16 | ~7 min to 13 replicas, then clean | 2973 | 7934 (window avg) / **2425 once converged** | 10,630 (whole run) | 0.78% avg (window) / 0.49<!--FM70-->% steady phase | $0.00121<!--FD81--> | scale-out lag, not a ceiling |
| 1000 | 828.3 (83%, window avg) · **998<!--FM60-->–1,001<!--FM61--> held 1m45s** | 6 / 30 | ~4 min to 30 replicas, then clean | 2092 | 6378 (window avg) / **2425 once converged** | 4,730 (whole run) | 4.97% avg (window) / 0.28<!--FM64-->% steady phase, 0.02<!--FM62-->% in the hold | $0.00088<!--FD82--> | scale-out lag, not a ceiling |

`$/1k queries` is gross: it is each point's own serving cost over its own queries, floor included,
so it falls with rate mostly because the always-on pair is spread over more traffic. It is not what
a query costs. That number is the campaign marginal in §4.2, $0.00375<!--FD65--> ᴰ/1k, netted once
against the day's resting inventory (D2) and 1.5<!--FD90-->–4.3<!--FD91-->× larger than any row here.

The 1000 row ran on a different configuration: `tei-embeddings` at `cpu 6 / 8` against the frozen
`3 / 4` every other row used (`02-inference` Matrix · `00-baseline` §2). It changed nothing about
the shape — the scaler's target is far below either limit — but the row is not a sixth point of
one series. Its `$/1k queries` carries the same divergence and is not bounded the same way: a
doubled per-pod request fits fewer pods per node, and this is the only point whose node mix is
dominated by `4xlarge`. Direction and magnitude are unmeasured.

Offered rate and served rate are reported separately, and at r500 and r1000 part of the gap is
the generator's. k6 schedules by the clock, but each scheduled iteration needs a free virtual
user, and the pool is sized off the 2000ms stub (rate × 2.5s, doubled). When the ramp pushed p95
to 25s, demand for slots ran several times over that cap and k6 dropped what it could not start:
32,045<!--FM71--> of 300,000 scheduled at r500 (10.7<!--FD145-->%) and 30,985<!--FM65--> of
600,000 at r1000 (5.2<!--FD144-->%), both with the pool pinned at its ceiling
(2,500<!--FR31--> and 5,000<!--FR30--> VUs). So neither window average reads the system: each
mixes the scale-out ramp, the generator's own shortfall and, at r1000, a three-minute stall.
What the two points held once converged is in §3.7; the ramp itself is convergence speed rather
than a ceiling (`02-inference` §3 Notes). The real campaign cost ($0.00375<!--FD65-->/1k queries,
CUR actual, `02-inference` §3) runs 1.5–4.3× higher than every `$/1k queries` figure in this table.
Those are per-point provisional reads that miss NAT entirely, along with the floor and settle
time between points. They are kept only to compare rates with each other, not as absolute costs.

**Two latency columns, because neither instrument answers the question alone.** Envoy's figures
are read at the gateway over any window asked for, but its buckets jump 1000 → 2500ms and every
response in this campaign lands inside that one bucket, so `histogram_quantile` interpolates:
`1000 + 0.95 × 1500 = 2425`. That is the printed number, arithmetic rather than measurement, which
is why four rates share it to the millisecond. The same interpolation puts p50 at 1672ms, below
the 2000ms stub every request pays, which is impossible for a constant delay. The k6 column is per
request and exact, measured from outside the VPC, so it also carries the internet round trip and
the load balancer and should read *higher* — it reads 300-400ms lower, which is the size of
Envoy's overstatement. It has one limit of its own: k6 summarises a whole run, so for r500 and
r1000 its p95 is dominated by the minutes of scale-out and the hold cannot be cut out of it. For
those two rows the honest reading is Envoy's converged figure, with the overstatement understood.
p99 was never queried at either instrument.

The sweep climbs from below and stops at the target rather than pushing to a throughput ceiling.
Past capacity an open-loop generator queues its own excess, and the measured p95 then grows with
the length of the run instead of describing the system. What the system does above the sustained
rate is a coverage row, not a number here.

The Matrix above carries offered rate against p95 and replicas.

### 3.7 Query capacity and constraint

- **Sustained rate** — 1000 req/s\*, held for 1m45s: 14:57:16–14:59:01Z, `tei-embeddings` at 30 replicas, 998<!--FM60-->–1,001<!--FM61--> req/s served, p95 flat at 2425ms, 0.02<!--FM62-->% errors. Over the full steady phase around it, to 15:01:01Z, the point served 955<!--FM63--> req/s at 0.28<!--FM64-->% errors, which does not meet `D15`'s 0.1<!--FR29-->% bound; that phase ends in a generator stall rather than a system limit. r500 is the same shape and thinner: 499<!--FM66-->–501<!--FM67--> req/s held for one minute at the same p95 floor, but at 0.25<!--FM68-->% errors, and no stretch of it meets the bound for longer than 30s; across its own phase it served 457<!--FM69--> req/s at 0.49<!--FM70-->%. Untested above 1000, so a lower bound rather than a proven ceiling
- **Capacity that rate required** — 6 API replicas and 30 embedding replicas at r1000, converged in ~4 min from the minimum of 2 each
- **Reference value** — the `p95 < 200 ms` line in `architecture.md` is a design target the stub makes unmeasurable: every request pays the frozen 2000ms Bedrock delay, so no p95 here can approach it. The retrieval-only path can still be read, from the generator's own per-request durations rather than from Envoy. Successful responses at the clean points have p95 2.04s (r050) and 2.06s (r300) with a median of 2.03s, measured from outside the VPC, so **retrieval plus the internet round trip is ~40-60ms** once the stub is subtracted — inside the target, though never isolated inside the cluster. Those are also the honest p95s: Envoy reads ~380ms higher at the same point because its buckets jump 1000 → 2500ms and `histogram_quantile` interpolates across the gap (`02-inference` M2), which is the same artefact that gives four rates an identical 2425ms in §3.6
- **Constraint** — no *sustained* ceiling found, by resource signature, up to 1000 req/s\*. `tei-embeddings` did reach 87-97.5% of its CPU limit (7.0-7.8 of 8 cores) during r1000's ramp, which `02-inference` Saturation calls a real momentary saturation; replicas relieved it and it did not return in the hold. `api` never exceeded 0.268 of its 0.5-core limit; Qdrant never exceeded 1.568 cores. Two limits on the claim: it is proven at the `cpu 6 / 8` request r1000 ran on, and the five rows at the frozen `3 / 4` publish no TEI CPU peak at all, where the same absolute usage would have been past the limit. With no sustained ceiling found there is nothing to relieve and no next scaling step to price

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
| query load only | 1000\* (§3.7) | 2425 | 6 / 30 (at r1000) | — |
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

One resting hour of a running, unloaded system, projected to a month at the published unit rates
(`docs/report/methodology.md` §9 · line-by-line audit in `00-baseline` §2 Floor). Split rather than totalled,
and fixed separated from what still moves at rest.

**As built** ᴰ

| Block | Line | Fixed | Variable at rest | Total |
| :--- | :--- | ---: | ---: | ---: |
| **B · Dedicated** | Qdrant node + gp3 (current-gen PVC) · serving pool at 2+2 replicas · Bedrock interface endpoints (removed in the right-sized column, `ADR-0018`) · S3 at rest · SQS polling | $533.20<!--FD23--> | $0.93<!--FD24--> | **$534.12<!--FD26-->** |
| A · Shared | EKS control plane · core node group · Karpenter on Fargate · NAT hourly · monitoring stack · the Gateway's load balancer | $333.59<!--FD21--> | $9.83<!--FD22--> | $343.42<!--FD25--> |
| **C · Total** | `A + B` | $866.79<!--FD27--> | $10.76<!--FD28--> | **$877.54<!--FD29-->** |

**Right-sized, same HA topology** ᴱ — `00-baseline` Right-sized floor · `docs/tech-debt.md` #5
and #12. The variable column is carried over unchanged: nothing in the right-size touches what
NAT and cross-AZ transfer move at rest.

| Block | Fixed | Variable at rest | Total |
| :--- | ---: | ---: | ---: |
| **B · Dedicated** | $410.39<!--FE8--> | $0.93<!--FD24--> ᴰ | **$411.31<!--FE9-->** |
| A · Shared | $316.60<!--FE7--> | $9.83<!--FD22--> ᴰ | $326.43<!--FE16--> |
| **C · Total** | $726.98<!--FE10--> | $10.76<!--FD28--> ᴰ | **$737.74<!--FE11-->** |

Block B right-sized, $411.31<!--FE9--> ᴱ, is the number §5's budget alarm is set against. That is a floor the
system is not running at today, chosen deliberately so the alarm tracks the target rather than
the defect.

The bill agrees that the headroom is there. In the resting hour the six nodes cost
$0.8298<!--FD129--> ᴰ, and CUR's split cost allocation assigns only part of that to pods: the rest,
$0.4938<!--FM58-->, is **59.5<!--FD130-->%** of node spend that no pod requested. Read it as a lower
bound, not as measured idleness — AWS apportions an instance across its pods by resource
*request*, so a pod asking for three cores and using a fifth of one counts as requested in full.
The right-sized column above was built the other way round, from observed working sets, and the
two readings point the same way from opposite directions.

Block B is what leaves the bill if the feature is deleted. It is not divided across an assumed
number of co-tenant features, because that divisor would be arbitrary and blocks B and C already
answer both questions a reader can ask. That criterion is what puts the Gateway's load balancer in
A rather than B, decided 2026-09-26: the Gateway lives in `rag-platform`, admits routes from every
namespace and already carries a second one, `/monitor` to Grafana, so deleting the feature leaves
it standing. Block C is unaffected, and the same NLB's three public addresses were already in A. Lines that carry no resource-level tag are not
allocated to a block: each is mapped by hand to the Floor row that already prices it, and takes
that row's block (`R5`, marked ᴿ). Untagged money here is not separate money — it is the same
money the Floor prices by resource, seen through the tag column — so the mapping moves no total.
They are 25.6<!--FD126-->% of everything billed in the resting
hour above (`R5`/`M2`, `00-baseline`), and that share is a reading rather than a threshold:
everything in this deployment that can carry a `feature` tag carries one, so what arrives untagged
is AWS-managed flat charges rather than a gap in this project's tagging (`00-baseline` §2). Most of
the share is one defect, not sizing — the CloudWatch vended-log line, which §4.2 excludes from every
Floor figure; net of it the untagged share is 17.9<!--FD127-->%.

*The NAT gateway* is the hidden line of this architecture class and is missing from almost every
published version of it. It is billed hourly regardless of traffic, and again per gigabyte
processed, including image pulls and model weight downloads. The hourly charge is floor; the
per-gigabyte charge appears again in §4.2 as a marginal line.

*Interface VPC endpoints are the second hidden line.* Each is billed per hour per availability
zone, before a byte moves — which is exactly why both were removed (`ADR-0018`, §4.5): a fixed
$26.28/month each that a per-gigabyte discount only repays 55x above this system's design volume.

*Quantization sets the database instance class.* At 1M points × 384 dimensions, an INT8-quantized
resident copy needs 0.384 GB against 1.536 GB for float32 ᴰ, which is why a `.large` node holds
the collection at all. It does not make this line small: the measured Qdrant working set at
teardown was 379 MiB (`qdrant-0`) and 97.7 MiB (`qdrant-1`) ᴿ against r7g.large's 16 GB, and that
unused memory is exactly what the right-size above removes by moving to c7g.large
(`docs/tech-debt.md` #5). The ~4x asymmetry between two replicas of the same collection is
unexplained and was not chased this pass. Either reading is an upper bound rather than a matching
figure, because it includes page cache on memory-mapped segments. The
retrieval cost of that compression is not measured here.

*The query path is why the serving line exists.* Both deployments hold two replicas at zero
traffic, because a request arriving at zero replicas pays a cold start. §3.7 states what that
permanently-on capacity buys in requests per second before the autoscaler has to act.

*Article 1 advertised "$0.00 on idle."* This table shows how many lines that holds for: 3 of the
22 items the Floor prices are ~$0 at idle (S3, SQS, Qdrant snapshot storage, which share one row),
and every compute, node-group and endpoint line is nonzero spend. The claim was about the elastic ingestion tier but reads as if it
covers the whole system, so both numbers are stated here.

### 4.2 Marginal

Floor lines are excluded by definition. At the sweet spot (N=25, `01-ingestion/M12`, pulled
2026-09-09), three components come from one clean, non-overlapping source
(`split_line_item_split_cost` per pod) and the fourth row is the residual, derived as the
$24,875<!--FD37--> total minus those three. It does not decompose further with the data available,
so it is stated as a gap instead of being forced into rows that would not add up.

The total and the components are also in different currencies, and the residual carries the
difference. The total is **cash**: `cur_marginal` plus `D23`, money that left the account. The
three component rows are **apportionment**: AWS split cost allocation dividing one node bill among
the pods on it by their requests, which moves money between pods without the bill changing. At
N=25 the embedding tier went from 2 replicas to 4 on the pair of nodes that was already running,
so the cash it caused is `D23`'s $0.01<!--FM24-->/run (§3.1's `TEI $`) while its apportioned share
is $0.249<!--FD153-->/run. Both are correct answers to different questions — what left the account, and who
occupied the capacity — and the share column below is a share of the total, not a share of cash.

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
| Floor share at the sustained rate | $0.000203<!--FD45--> ᴰ (best case; negligible only because 1000 req/s continuously is a huge volume) | — |
| Bedrock generation, at ~1,800<!--FE1--> input and up to 512<!--FR17--> output tokens | ~$0.51<!--FD39--> ᴱ | — |

The three lines answer different questions and are not summed into a headline. The marginal
total is what an additional query costs once the tier is already scaled. It uses the campaign
CUR read (`02-inference` §3), not the per-point provisional `D16` figures in §3.6, which
understate it 1.5–4.3× because they miss NAT entirely and the floor and settle time between points.
The floor share assumes the tier runs at the sustained rate (1000 req/s\*) continuously, which
makes it an extreme best case: it is negligible only because 1000 req/s continuously serves
2,628,000,000<!--FD116--> queries/month. At every volume in the §4.3 table the floor dominates
instead; the crossover there is ~148M queries/month, far above anything swept. The generation line is a vendor
rate applied to a token count nobody swept, derived from the real prompt template
(`apps/api/core/llm.go`, `02-inference/E18`). No run called the provider. If generation is turned
on, it would be ~136<!--FD115-->× the marginal retrieval cost, the largest line in the query-path
cost and the one this report can least confirm.

### 4.3 Amortization

`Effective $/unit = ( Block B + Marginal × V ) ÷ V`. Arithmetic on §4.1 and §4.2, no run. Block
B is the right floor: for a feature on a cluster that exists anyway, the question is what this
feature costs to keep alive, not what the platform costs.

Each table below charges the whole of Block B. They are two readings of the same floor under
two different denominators, and they are not addends: adding a `$/doc` row to a `$/query` row
counts the same monthly floor twice. The conversion that would make them additive needs an
arrival ratio nobody measured.

Uses Block B = $534.12<!--FD26-->/month and the sweet-spot marginal rate, $24,875<!--FD37-->/1M docs = $0.02488<!--FD38-->/doc.

| Monthly documents | Effective $/doc ᴰ | Floor share |
| :--- | :--- | :--- |
| 1 000 | $0.5590<!--FD92--> | 95.6<!--FD96-->% |
| 10 000 | $0.0783<!--FD93--> | 68.2<!--FD97-->% |
| 100 000 | $0.0302<!--FD94--> | 17.7<!--FD98-->% |
| 1 000 000 | $0.0254<!--FD95--> | 2.1<!--FD99-->% |

Uses Block B = $534.12<!--FD26-->/month and the real campaign marginal rate, $0.00375<!--FD65-->/1k queries = $0.00000375<!--FD100-->/query.

| Monthly queries | Effective $/query ᴰ | Floor share |
| :--- | :--- | :--- |
| 10 000 | $0.05342<!--FD101--> | 99.99<!--FD105-->% |
| 100 000 | $0.00534<!--FD102--> | 99.93<!--FD106-->% |
| 1 000 000 | $0.000538<!--FD103--> | 99.3<!--FD107-->% |
| 10 000 000 | $0.0000572<!--FD104--> | 93.4<!--FD108-->% |
| 500 000 000 | $0.0000048<!--FD139--> | 22.2<!--FD141-->% |
| 1 000 000 000 | $0.0000043<!--FD140--> | 12.5<!--FD142-->% |

Below ~21,472<!--FD41--> documents and ~142,547,228<!--FD43--> queries per month, the volumes where floor share drops
under half, you pay mostly for the feature to exist rather than for work done. Those two volumes
are the lower bound of where this design makes economic sense. Ingestion crosses 50% floor share
at a modest volume because its marginal cost per unit is comparatively large. The query path's
marginal cost per unit is three orders of magnitude smaller, so its crossover sits at a rate the
design has to be built for rather than a volume it might reach.

**The query rows assume an arrival rate, and the low ones are out of the regime the rate was
measured in.** A month holds 2,628,000<!--FR28--> seconds (730 hours), so the four smallest rows are
0.004<!--FD146-->, 0.04<!--FD147-->, 0.4<!--FD148--> and 3.8<!--FD149--> requests a second sustained. The marginal was measured over a campaign that ran at 50 to 1000,
where `tei-embeddings` scaled from 2 replicas to 30 and paid for the nodes underneath them. At 0.4
requests a second nothing scales: the resting pair answers everything, no node is ever added, and
the only marginal left is NAT bytes. So those rows overstate the marginal and their floor share is
a lower bound, which makes the conclusion stronger rather than weaker. The three rows that do sit
inside the measured range are the crossover at 54<!--FD143--> requests a second, 500M a month at
190<!--FD150--> (r200 served 192.5) and a billion at 381<!--FD151--> (between r300 and r500), and they are
the ones to read. Above
the crossover the marginal takes over quickly: the floor is down to 22.2<!--FD141-->% of the bill at
500M and 12.5<!--FD142-->% at a billion, so most of what is paid there is work rather than standing
cost.

`api` is not what drives that. It held 2 replicas to ~300 requests a second and reached 6 only at
828, never passing 54% of its CPU limit (§3.7). Every replica the marginal pays for above the
crossover is an embedding replica.

### 4.4 Conditional alternatives

Two alternatives to what was built, neither chosen: each pays off only above a condition this
deployment sits below.

#### Fargate instead of Karpenter Spot, ingestion

The same two ingestion Jobs, billed per vCPU-second instead of per node, at the N=25 sweet spot.
Pod-hours, cell sizing and rates are in `01-ingestion/D29`; the shared embedding tier stays
outside it.

| | Karpenter Spot ᴰ | Fargate ᴰ |
| :--- | ---: | ---: |
| Chunker | $0.0021<!--FM48--> | $0.0174<!--FD119--> |
| Indexer | $0.2574<!--FM49--> | $0.7387<!--FD120--> |
| **Both workers, one run** | **$0.2595<!--FD122-->** | **$0.7562<!--FD121-->** |

Fargate's 2.91<!--FD123-->× premium removes node provisioning and its warm-up tail (§3.4), the
per-node image pull and the Spot interruption path in the workers. Whether that is worth three
times a worker bill that is a small part of the floor either way (§4.1) is a judgement about
operational load. The multiple is if anything too low for Fargate, which meters image pull per
task and has no Spot capacity type on EKS.

**Condition:** ingestion owning more than 34<!--FD124-->% of the $1.4787<!--FM50--> of
provisioned-but-unoccupied capacity the Spot side carries at N=25. That figure is fleet-wide and
§3.4 declines to split it by workload; above that share Spot costs what Fargate does.

#### VPC endpoint instead of the NAT gateway, query path

The baseline is the NAT gateway §4.1 already pays for. At a reference 1,000,000<!--FE14--> queries
per month, `02-inference/E18`'s 2,312<!--FD117--> tokens per query weigh 11.4<!--FD52--> GB on the
wire:

| | Via NAT | Via the endpoint |
| :--- | ---: | ---: |
| Network | $0.59<!--FD53--> ᴱ | $26.39<!--FD54--> ᴱ |
| Generation | $508.64<!--FD51--> ᴱ | $508.64<!--FD51--> ᴱ |
| Network as a share of generation | 0.12<!--FD55-->% ᴱ | — |

The endpoint's three ENIs cost $26.28<!--FD48-->/month whatever the traffic, and its data rate is
$0.01<!--FR15-->/GB where the NAT charges $0.052<!--FR4-->. It repays that fixed cost at
625.71<!--FD49--> GB/month, which at 12,248<!--FD40--> bytes a query is 54,854,311<!--FD50--> ᴱ
queries per month — **55x the reference volume**, and a volume the sweep never approached. Below
it the endpoint costs more than the NAT it replaces.

`ADR-0007` chose the endpoint on a privacy boundary and on "slashes NAT Gateway data processing
charges". The second is measured false by the margin above. **`ADR-0018` removes both endpoints**:
the cost claim is wrong, and the privacy boundary is not worth $26.28/month at this volume — nor
was it ever in effect, both endpoints being in `eu-central-1` while the client calls `us-east-1`.
Generation now egresses through NAT, protected by TLS and IAM rather than by a VPC perimeter, and
no claim to the contrary stands in this report. Every byte figure is estimated; `02-inference/K4`
carries the assumptions and their biases, and one real generation run replaces all three at once.

The same reading settles two defects without a run, both `docs/tech-debt.md` #12: the `bedrock`
control-plane endpoint, $26.28<!--FD47-->/month of `block_b_fixed`, is reachable by nothing, and the
runtime endpoint's private DNS never matches the hostname the client resolves. `ADR-0018` closes
both by deletion rather than by repair, and the endpoints are gone from `vpc.tf` as of 2026-09-28.

---

## 5. Guardrails

- **Ingestion concurrency ceiling — recommend `maxReplicaCount: 20` ᴱ**

  Derived from §3.3 sweet spot · `01-ingestion` Guardrails · enforced in
  `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml`

  This is below the N of four of the five points swept, which is the point: N is a cap, not an
  observed concurrency (§3.1), and the chunker never exceeded ~20 at any N. The sweet-spot run
  (N=25) held a time-weighted mean of 19.5, so its cap bound only at the peak. No point separates
  20 from 25, so this is not a claim that 20 is cheaper, and it holds for this corpus only (the
  chunker's ~20-concurrent ceiling is corpus-driven). The live value was raised from 10 to 20 to
  match, 2026-09-19, on both ScaledJobs; it applies at the next cluster bootstrap.

- **Chunker memory limit — keep `1Gi`**

  Derived from `01-ingestion/M7`, valid only where `M8` is zero · enforced in
  `deploy/k8s/apps/chunker`

  `M8` = 0 by live observation (`01-ingestion/metrics.md` M8). Peak working set over the five swept
  points is 445<!--FM79--> MiB, at N=25, so the limit holds 2.30<!--FD156-->× the observed maximum.
  `peak+30%` would put it at 579 MiB; the extra margin is deliberate and stated in the manifest —
  the sample corpus's largest file is 78.8 MB while the full corpus has one up to 124 MB, and an
  image-heavy PDF decodes to several times its file size. The chunker is short-lived, so the 15s
  scrape under-samples it at N=50, 75 and 125, where 1-3 pods were caught against 20 at N=25.

- **Indexer memory limit — keep `4Gi`; raise `requests.memory` to `2560Mi`**

  Derived from `01-ingestion/M7`, valid only where `M8` is zero · enforced in
  `deploy/k8s/apps/indexer`

  `M8` = 0 by live observation (`01-ingestion/metrics.md` M8). Peak working set 2,219<!--FM80--> MiB,
  at N=75, so the limit carries 1.85<!--FD157-->× headroom and holds. The request is the line that
  moves: at 2,048<!--FR37--> MiB it sits *below* that peak, so the pod routinely uses more than it
  asked for. That costs nothing in OOM terms, but it makes the indexer the first eviction candidate
  under node memory pressure, and §2.3's packing density is computed from the request rather than
  from what the pod uses, so the real density is lower than that range states.

- **Node consolidation delay — `apps-compute: 5m`, `WhenEmpty`, not revised**

  Derived from §3.4 unoccupied-capacity share · enforced in `apps-compute` NodePool

  §3.4's unoccupied-capacity number is fleet-wide and too coarse to argue for a different value.

- **Go API replica ceiling — live `maxReplicaCount: 10`**

  Derived from §3.7 replicas at the sustained rate, plus margin · enforced in `api-scaler`

  6 replicas were observed at r1000 (D15's lower bound), so some margin exists, but D15 is untested
  above 1000 req/s\* and the setting isn't confirmed sufficient at a higher rate.

- **Embedding tier replica ceiling — keep live `maxReplicaCount: 30`**

  Derived from §3.7 replicas at the sustained rate · enforced in `tei-embeddings-scaler`

  It was fully used at r1000 with zero margin, and it carried that rate: 30 replicas held
  1000 req/s\* for 1m45s at the steady-state p95 and 0.02<!--FM62-->% errors (§3.7), which is the
  rate this deployment is sized for. §2.3 records why a point sitting at its ceiling is kept rather
  than excluded. No quota increase is requested. Above 1000 req/s the cap binds first, then this
  account's Spot vCPU quota (`L-34B43A08`=256). What that quota allows depends on the per-pod
  request, so it is not one number: ~35-40 replicas at the `cpu 6` request `r1000` ran on, and
  roughly twice that at the frozen `cpu 3` the code carries (`00-baseline` §2 Configuration
  freeze).

- **Go API memory limit — keep `512<!--FR32-->Mi`**

  Derived from `02-inference/M6` · `Q8` · enforced in `deploy/k8s/apps/api`

  Across the sweep the fleet peak is 165<!--FM76--> MiB, 3.10<!--FD154-->× under the limit — but the
  fleet is not the binding case. One replica taking the whole offered rate reached
  439<!--FM77--> MiB, 86% of the limit (`M6`, a pinned-replica reading rather than a fleet point),
  and that state is reachable at scale-in and under the imbalanced routing seen at `n100-sticky`.
  The limit is sized for that case, not for the average.

- **Embedding tier memory limit — keep `1Gi`**

  Derived from `02-inference/Q8` · enforced in `deploy/k8s/apps/tei`

  Peak working set 670<!--FM78--> MiB, at r050 on 3 replicas — per-pod memory runs highest when
  fewest pods share the load — so 1.53<!--FD155-->× headroom. Memory decides nothing else here: at
  `requests.cpu: 3000m` one pod fills an xlarge node's CPU, so packing is CPU-bound, and the memory
  request of 768<!--FR34--> MiB, which sits tighter against the peak than the limit does, has no
  effect on density.

- **Query rate alert — fire at 1000 req/s\* served, or when `tei-embeddings` sits at
  `maxReplicaCount: 30`**

  Derived from §3.7 sustained rate · §2.3 · enforced in `prometheus/rules.yaml`

  The alert marks the edge of the measured envelope, not a capacity limit. `D15` is a lower bound
  on what the system can serve, so it says nothing about where the system fails. It is exactly
  where the measured data ends: at r1000 the embedding tier used all 30 of its replicas, so above
  that rate there is no autoscaling headroom left and no run that shows what happens. Either
  condition means the deployment is running outside what this report proves. How long a condition
  must hold before the alert fires is a choice, not a measurement.

- **Latency SLO alert — retrieval p95 above 200ms**

  Derived from §3.7 reference value · `architecture.md` design target · enforced in
  `prometheus/rules.yaml`

  The threshold is the design target, not a number fitted to this campaign. Every gateway p95 here
  includes the fixed 2000ms Bedrock stub, and a threshold tuned against it would not transfer to
  real traffic. The target is attainable: the generator's per-request durations put retrieval plus
  the internet round trip at ~40-60ms once the stub is subtracted (§3.7). The rule needs two things
  before it can fire meaningfully. The first is a retrieval-only latency series, because Envoy's
  request latency includes generation. The second is histogram buckets around 200ms, because
  Envoy's buckets jump 1000 → 2500ms and `histogram_quantile` interpolates inside one bucket
  (§3.6). An end-to-end SLO that includes generation needs one real-Bedrock calibration run
  (`docs/tech-debt.md` #9).

- **Ingestion backlog alert — drain rate below 0.76 docs/min while the backlog is non-empty**

  Derived from §3.1 run matrix (slowest measured point, N=10) · enforced in `prometheus/rules.yaml`

  0.76 docs/min is the slowest drain any configuration in the sweep produced. The guardrail
  concurrency sits above N=10, so the pipeline is expected to drain faster than that. A non-empty
  backlog draining slower is running below every measured configuration: a stalled worker, a
  throttled dependency, or a scaler that is not adding pods. The rate is read the way §3.1 reads
  it, as the derivative of queue depth, which catches a run that stalls rather than draining
  steadily. This alert detects a stall, not a missed deadline: a staleness SLO needs a stated
  tolerance for ingestion delay, and no requirement in this project defines one. The evaluation
  window is a choice; the sweep measured docs/min over whole runs of 38.5-132.5 min.

- **Do not move the query path to a VPC endpoint on a cost argument — crossover
  54,854,311<!--FD50--> ᴱ queries/month**

  Derived from §4.4 · enforced in `terraform/` VPC endpoints, `ADR-0007`

  The reference volume is 1,000,000<!--FE14--> queries/month. Below the crossover the endpoint
  costs more than the NAT it replaces, so the decision rests on the privacy boundary in `ADR-0007`
  alone. The figure is estimated, not measured (`02-inference/K4`), so treat it as an order of
  magnitude.

- **NAT topology — set `single_nat_gateway = false` ᴰ**

  Derived from §4.1 Floor · `ADR-0017` · enforced in `terraform/variables.tf`

  A NAT gateway is zonal and does not fail over, so the single gateway the floor was measured on
  makes one zone a point of failure for node join (Cilium's image is pulled from a public
  registry, so a node without egress never leaves `NotReady`), for every image pull, and for the
  `ec2`, `ssm`, `sqs`, `s3` and `sts` APIs at once — the cluster freezes at its current size in
  all three zones, not just the lost one. Removing the dependency instead of duplicating the
  gateway costs more than duplicating it and is a project rather than a setting (`ADR-0017`), so
  this is the only available answer. One gateway per zone is $113.88<!--FD132--> against
  $37.96<!--FD5-->, plus two more Elastic IPs at $7.30<!--FD135-->, so
  **+$83.22<!--FD136-->/month**, 11.3<!--FD134-->% of the right-sized floor. That sits outside the
  floor rather than inside it: the right-sized column changes sizes and keeps the topology, and a
  gateway per zone is a topology change. `single_nat_gateway = true` stays available for
  development.

- **Budget alarm — recommend $575.84<!--FD56--> ᴱ/month**

  Derived from §4.1 · enforced in `terraform/budgets.tf` (not yet created)

  Right-sized Block B × 1.4 = $411.31<!--FE9--> × 1.4. Set against the right-sized floor rather
  than the as-built one, so the alarm tracks the target the tech-debt items move toward instead of
  pinning today's defects in place; the as-built floor would put it at $747.77<!--FD57--> ᴰ (per
  D1, both columns are carried). `terraform/budgets.tf` does not exist, so nothing enforces this
  today (`docs/tech-debt.md` #11).
