# Executive Engineering Report — simple-rag

This report measures cost and performance on both paths of a RAG system: asynchronous
document ingestion and synchronous queries. It also shows what the system costs at rest and
how that cost spreads over volume.

- **Report** — `simple-rag` · v1.0 · 2026-09-09
- **System under test** — chunker `sha-404a267` · indexer `sha-32365dc` · api `sha-bafdc1f` · tei
  `cpu-1.6` · commit `1ef1f0a8`, 2026-09-05. TEI ran at `cpu 6 / 8` for r1000 only, `3 / 4`
  everywhere else (§3.2)
- **Scope** — text-layer PDF corpus, bulk drop · N ≤ 125 concurrent ingestion pods · R ≤ 1000 req/s\* · EKS + Karpenter,
  KEDA (serving from 2 replicas, ingestion from zero), self-hosted Qdrant, TEI `bge-small-en-v1.5` · `eu-central-1`
- **Executions** — `00-baseline` · `01-ingestion` · `02-inference`, raw data in
  `executions/*/data/`
- **Cost source** — AWS Cost and Usage Report 2.0 · USD · method in `methodology.md` §8
- **Figures** — measured unless marked: ᴰ derived · ᴿ recorded · ᴱ estimated
- **Supersedes** — —
- **Changes** — first revision

---

## Coverage

| Area | Status | Evidence |
| :--- | :--- | :--- |
| Ingestion throughput, cost per run and cost per 1M documents | measured · cost per run derived ᴰ · per 1M documents estimated ᴱ | §3.1 · `01-ingestion` Notes, CUR table · `D25` |
| Per-component share of ingestion cost | derived ᴰ | §4.2 · `01-ingestion` Notes, CUR table |
| TEI cost caused by ingestion | measured | §3.1 `TEI $ (cash)` · §4.2 · `01-ingestion/D23` |
| Ingestion constraint | measured | §3.1 · `01-ingestion/M6` |
| Sustained query rate, the replicas it required and the query path constraint | measured | §3.2 · §2.3 · `02-inference/D15` · `Q7` · `R14` · CloudTrail in `02-inference/data` |
| Retrieval cost per 1k queries at 1000 req/s | estimated ᴱ | §4.2 · `02-inference` r1000 steady phase · campaign CUR |
| Generation cost per 1k queries — Bedrock | estimated ᴱ | §4.2 · `02-inference/E18` |
| Idle floor, split A / B / C | derived ᴰ as built · estimated ᴱ right-sized | §4.1 · `00-baseline` §2 Floor |
| Errors found at rest, excluded from the floor | derived ᴰ | §4.1 · `00-baseline` §2 Floor errors table |
| Amortization across volumes — documents | estimated ᴱ | §4.3 |
| Amortization across volumes — queries, generation included | estimated ᴱ | §4.3 · `02-inference/E18` |
| Fargate against EC2 Spot nodes, ingestion | estimated ᴱ against the nodes that ran | §4.4 · `01-ingestion/D29` |
| Warm-up and consolidation-tail share | partly measured | NAT, SQS and S3, almost all of it image pulls while nodes start, are 55.8<!--FD171-->% of the N=25 run (§4.2). Node boot and teardown time itself was not measured |
| Next ingestion bottleneck after the indexer fix | declared, not measured | what limits throughput once the indexer processes documents in parallel: TEI or Qdrant writes. Their metrics were not collected (`01-ingestion` M15–M17). TEI's serving pool already touched its 100 vCPU limit at N=125 (§5.2) |
| Ingest and query contention on shared Qdrant and TEI | declared, not measured | how query latency and errors change while ingestion runs in parallel |
| Scaler tuning — thresholds and cooldowns | declared, not measured | how much of convergence time is configuration rather than node provisioning |
| Query tail latency, p99 | declared, not measured | how slow the slowest 1% of queries get |
| Retrieval quality against quantization | declared, not measured | what INT8 compression costs in recall. INT8 SQ is a frozen given here |
| Behaviour above the sustained rate | out of scope | whether overload degrades or collapses the deployment |
| End-to-end latency including Bedrock generation | out of scope | what a user waits for once Bedrock answers |
| Reliability economics — Spot interruption under load | out of scope | the price of the resilience mechanism: work lost, duplicates, recovery time |
---

## 1. BLUF

* **Ingestion cost at the sweet spot** — $24,875<!--FD37--> / 1M docs ᴱ at N=25. N=10 below it costs
  $44,707<!--FD76--> ᴱ, and every N above it costs more. Fargate for the same two workers would cost
  about 1.4<!--FE21--> ᴱ times as much as right-sized Spot nodes (§4.4)
* **Sustained query rate** — 1000 req/s\*, held for 1m45s on 11<!--FM90--> TEI pods of 6 cores, with the
  serving pool at its 100<!--FR38--> vCPU limit, and 0.02<!--FM62-->% errors. The full steady phase served 955<!--FM63--> req/s at 0.28<!--FM64-->%
  errors and misses the 0.1<!--FR29-->% error bound (`D15`). Without generation a query returns in ~40-60ms
  at p95 (§3.2)
* **Retrieval cost** — ~$0.0008<!--FE18--> / 1k queries ᴱ at 1000 req/s\*, ~$2,077<!--FE19--> ᴱ a month,
  priced from the nodes that held that rate (§4.2). Generation is not included (Verdict)
* **Idle floor, Block B (dedicated to this feature)** — $534.12<!--FD26--> / month ᴰ (Block C total: $877.54<!--FD29--> ᴰ). This
  is what the feature costs with zero traffic on a platform that exists anyway

\* **1000 req/s** means the 1m45s hold above, not the r1000 window and not a proven ceiling (§3.2).

**What the measurements settled**

* **Ingestion is limited by code, not by hardware.** Nothing saturated at any N. The sequential
  loop in `apps/indexer/src/main.py` holds one TEI call in flight per pod, so throughput follows
  replica count: TEI rose to 26 replicas for 2.60 docs/min at N=125, and docs/min was
  still climbing when testing stopped on cost. Raising it takes a rewrite of that loop, not larger
  pods.
* **The serving pool reached its CPU limit at 1000 req/s, and Qdrant is the nearest ceiling behind it.**
  The `apps-serving` NodePool sat at its 100<!--FR38--> vCPU limit in r1000, so TEI could not grow past
  11<!--FM90--> pods (§2.3). Qdrant reached 1.568<!--FM59--> of its 2<!--FR27-->-core limit,
  78<!--FD137-->%, and cannot scale out: two replicas hold one shard at every rate.
* **The defects cost more than the sizing.** Errors found at rest recur at $175.85<!--FD35-->/month
  (§4.1). Right-sizing every line in the floor saves $139.80<!--FD138--> ᴱ, and $52.56 of that is
  the two Bedrock endpoints, which count as defects, so sizing alone saves $87.24<!--FD152--> ᴱ.
* **Ingestion has one cheap operating point.** Cost per document rises on both sides of N=25, to
  $88,161<!--FD72--> ᴱ per 1M docs at N=125, so concurrency beyond it buys speed at a steep price (§3.1).

**Verdict** — **ship with guardrails.** Nothing found here blocks release. Both paths held the
volumes tested, but the query path has no headroom above 1000 req/s\* until the serving pool's CPU
limit rises (§5.2). Two of §5's values are conditions of release: the budget alarm at
$1,032.84<!--FD56--> ᴱ/month and ingestion max replicas at 20 ᴱ. Two gaps ship
declared. Generation cost, ~$0.51<!--FD39--> ᴱ per 1k queries, is an estimate no run has
confirmed, and at ~644<!--FD174--> ᴱ times the retrieval cost it is the largest number in the
query path (`docs/tech-debt.md` #9). The Fargate comparison covers N=25 only (#10). Every
query-path finding holds for an idle ingestion path, because contention was not tested (Coverage).

---

## 2. Test Setup & Scope

### 2.1 Ingestion — per document

- **Unit of work** — one source document, complete when its last chunk is upserted and counted in Qdrant `points_count`
- **Workload fixture** — 100-file / 1.38GB stratified sample (~9.5% of the full corpus, 10 size deciles, seed 42), bulk drop · median 8.77MB, p95 49.23MB · frozen at commit `bafdc1f` (2026-08-31, `00-baseline` §2)
- **Denominator** — 100 documents (files), frozen with the fixture. The same corpus is reloaded at every point, confirmed by an identical 84,018-chunk `points_count` (R21) at every point
- **Window** — opens at the first `s3:ObjectCreated`, closes when the ingestion pool reaches zero nodes and TEI returns to its always-on minimum, plus five minutes. Upload is outside the system under test

### 2.2 Query path — per query

- **Unit of work** — one search request, complete when the retrieved context is written to the response. Generation in Bedrock is outside the unit
- **Workload fixture** — 5 fixed query strings (`docs/report/scripts/load.js:57-63`), selected uniformly at random per request, replayed at a constant arrival rate against the collection produced by `01-ingestion`
- **Denominator** — queries served inside the steady phase, produced by each run rather than frozen
- **Window** — the whole generator run. It opens with both deployments at their always-on minimum, so it includes the scale-out. The designed 60s stability check was not enforced: the preflight checks one instant (`02-inference` §2)
- **Steady phase** — the part of the window after replicas converge
- **Hold** — the longest stretch of the steady phase that serves the offered rate at a flat p95
- **Run names** — `rN` is the run offered N req/s, as in r1000

### 2.3 Conditions shared by both

- **Scope** — `00-baseline` §2 Scope
- **Metric sources** — `00-baseline` §1 · `01-ingestion/metrics.md` · `02-inference` §1
- **Autoscaling** — the Go API and TEI scale from two replicas each, their always-on minimum, under the triggers frozen in `00-baseline` §2. Every figure in this report is conditional on those triggers rather than on a replica count. On the ingestion path the ScaledJob max replicas is the swept axis N, so the indexer running at N is the design, not a ceiling. TEI stayed under its own max replicas there, 26 of 30 at N=125. At r1000 TEI ran on 11<!--FM90--> pods of 6 cores, the most the `apps-serving` NodePool could hold at its `cpu: 100` limit, which CloudTrail shows it reaching (100<!--FM92--> vCPU, `02-inference/data`). `02-inference`'s validity rule excludes a point that sits at its ceiling, and this one is kept as the declared exception: it held the offered rate at the steady-state p95 with 0.02<!--FM62-->% errors (§3.2), so 11 pods sufficed
- **Shared embedding service** — TEI (`tei-embeddings`), one deployment serving both paths. Ingestion runs raise its replica count, and that cost is charged to ingestion in §4.2 after the always-on minimum is subtracted
- **Worker packing density** — the ingestion pool is pinned to one Spot instance family, `c7g`, in three sizes (`xlarge`, `2xlarge`, `4xlarge`) so Karpenter can fall back when one Spot pool runs out of capacity. That gives ≈ 3–14 indexer pods per node, computed from frozen requests against allocatable, memory-bound, never observed live (`01-ingestion` §2). Every ingestion figure is conditional on this ratio
- **Scalar quantization** — INT8 SQ is a fixed parameter, chosen for memory footprint. Its effect on retrieval quality is not measured and is not claimed either way

---

## 3. Efficiency Frontier

### 3.1 Ingestion — throughput, cost and constraint

Tested at N = 10, 25, 50, 75 and 125. N=25 was the nearest to sweet spot, the cheapest operating point
at $24,875<!--FD75--> ᴱ per 1M docs. Throughput is limited by the indexer's code, not by any resource. 

N is the max replicas setting (`maxReplicaCount`) on both ScaledJobs, a limit on concurrent pods,
not observed concurrency. The indexer ran at max replicas at every point (125 of 125 at N=125, `M5`).
The `chunker` peaked at ~20 whatever the N, technically because 100-file corpus was same.

Cost per document has V-shape, the cheapest at N=25 and both sides neighbors points are higher. N=10 costs
$44,707<!--FD76--> ᴱ per 1M docs against $24,875<!--FD75--> ᴱ at N=25, because it runs twice as
long (132.5 min against 61.7 min) while fixed per-hour costs keep billing.

Throughput rises at every step and never levels off. Per step, it gains +113%, +40%, +2.6%, then
+11.6%. If speed matters, stop at N=50: it buys +40% docs/min over N=25 for $19,460<!--FD77--> ᴱ
more per 1M docs.

Ingestion is limited only how the indexer calls TEI, not by any resource. No worker reached
its CPU or memory limit at any N (`01-ingestion/M6`). Each indexer pod sends one TEI request at a time and
waits for the answer before sending the next (`apps/indexer/src/main.py`). Its throughput depends mostly on how
long that call takes, so the only way to go faster today is more pods.

![Cost per 1M docs against throughput, one point per N](charts/tradeoff-jobs-navy.svg)

| N | Docs/min | Wall time | TEI peak | Compute $ | TEI $ (cash) | Other $ | $/run | $/1M docs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 10 | 0.76 | 132.5 min | 3 | $1.55<!--FM85--> | $0.31<!--FM25--> | $2.61<!--FD162--> | $4.47<!--FD71--> ᴰ | $44,707<!--FD76--> ᴱ |
| 25 | 1.62 | 61.7 min | 4 | $1.09<!--FM81--> | $0.01<!--FM24--> | $1.39<!--FD163--> | $2.49<!--FD70--> ᴰ | **$24,875<!--FD75-->** ᴱ |
| 50 | 2.27 | 44.0 min | 10 | $1.26<!--FM86--> | $0.29<!--FM23--> | $2.88<!--FD164--> | $4.43<!--FD69--> ᴰ | $44,335<!--FD74--> ᴱ |
| 75 | 2.33 | 42.9 min | 16 | $1.54<!--FM87--> | $0.52<!--FM22--> | $4.10<!--FD165--> | $6.16<!--FD68--> ᴰ | $61,573<!--FD73--> ᴱ |
| 125 | 2.60 | 38.5 min | 26 | $2.01<!--FM88--> | $0.82<!--FM21--> | $5.99<!--FD166--> | $8.82<!--FD67--> ᴰ | $88,161<!--FD72--> ᴱ |

### 3.2 Query path — sustained rate, latency and bottleneck

Tested at 50, 200, 300, 500 and 1000 req/s. The query path held 1000 req/s\* for 1m45s at r1000
(14:57:16–14:59:01Z, bold in the table). No component saturated, but the serving pool sat at its
NodePool CPU limit, with TEI on 11 pods (§2.3). Over the full steady
phase it served 955<!--FM63--> req/s at 0.28<!--FM64-->% errors, which misses the
0.1<!--FR29-->% error bound (`D15`).

r500 and r1000 has on average 0.78% and 4.97% errors over the whole run. Most of them
during scale-out, while TEI was still adding replicas. After replicas caught up, errors
settled at 0.49<!--FM70-->% and 0.28<!--FM64-->%, close to r200 and r300 (0.24% and 0.20%). That
residual is not explained by scale-out, and its cause is not confirmed. Part of the requests weren't
sent, as k6 skipped 10.7<!--FD145-->% and 5.2<!--FD144-->% of them during scale-out
([dropped iterations](https://grafana.com/docs/k6/v2.2.x/using-k6/scenarios/concepts/dropped-iterations/)),
and at r1000 it stopped sending for three minutes. Skipped requests lower the served rate but do
not count as errors.

Without generation, a query returns in ~40-60ms at p95. Every request has a fixed 2000ms stub
instead of the Bedrock call, and k6 measured 2.04s at r050 and 2.06s at r300 from outside the VPC.
The table carries two p95 readings. Envoy's is interpolated between its 1000 and 2500ms buckets,
so it reads 2425ms at every converged point, 300-400ms above k6. k6 is exact per request but reports
one figure per run, so at r500 and r1000 it includes the scale-out minutes.

Qdrant was the closest to the saturation point, it peaked at 1.568<!--FM59--> of 2<!--FR27--> cores.
TEI touched 97.5% of its CPU limit in r1000 while it was still scaling out, and the added replicas relieved it.
`api` peaked at 0.268 of 0.5 cores. r1000 is the only row where TEI ran with more CPU, `6 / 8` cores
instead of `3 / 4`, so its cost is not part of the same trend as the other rows.

**Run $/1k (gross)** — derived from node lifetimes in each run. It contains 2 baseline nodes but
  doesn't count NAT.

| Offered req/s | Served req/s | api / tei replicas | p95 ms ᴿ (Envoy) | p95 ms (k6) | Error % | Run $/1k (gross) ᴰ |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 50 | 45.5 (91%) | 2 / 3 | 2418 | **2040** | 0% | $0.00250<!--FD78--> |
| 200 | 192.5 (96%) | 2 / 7 | 2425 | **2150** | 0.24% avg / 4.0% peak | $0.00141<!--FD79--> |
| 300 | 296.4 (99%) | 3 / 11 | 2425 | **2060** | 0.20% avg / 2.75% peak | $0.00098<!--FD80--> |
| 500 | 398.7 (80%, window avg) · **499<!--FM66-->–501<!--FM67--> held 1 min** | 3 / 16 | 7934 (window avg) / **2425 once scaled out** | 10,630 (whole run) | 0.78% avg (window) / 0.49<!--FM70-->% steady phase | $0.00121<!--FD81--> |
| 1000 | 828.3 (83%, window avg) · **998<!--FM60-->–1,001<!--FM61--> held 1m45s** | 6 / 11 | 6378 (window avg) / **2425 once scaled out** | 4,730 (whole run) | 4.97% avg (window) / 0.28<!--FM64-->% steady phase, 0.02<!--FM62-->% in the hold | $0.00088<!--FD82--> |

---

## 4. Cost Structure

Monthly cost has three blocks. Block B is what RAG costs as a feature: everything that leaves the
bill if the feature is deleted. Block A is the shared platform, which stays either way. Block C is
A + B.

Each block has a floor: what it costs with zero traffic. Block B also has a marginal: what each
document or query adds on top of the floor.

**Block C** = Block A (floor) + Block B (floor + marginal)

### 4.1 Floor

The floor is measured as one hour of the running system with no load, projected to a month at AWS
list rates (`docs/report/methodology.md` §8 · line-by-line audit in `00-baseline` §2 Floor). Described in two
versions As built and Right-sized, as after the analysis we can choose the correct node sizes and exclude errors

**As built** ᴰ

| Block | Line | Fixed | Variable at rest | Total |
| :--- | :--- | ---: | ---: | ---: |
| **B · Dedicated** | Qdrant node + gp3 (current-gen PVC) · serving pool at 2+2 replicas · Bedrock interface endpoints (removed in the right-sized column, `ADR-0018`) · S3 at rest · SQS polling | $533.20<!--FD23--> | $0.93<!--FD24--> | **$534.12<!--FD26-->** |
| A · Shared | EKS control plane · core node group · Karpenter on Fargate · NAT hourly · monitoring stack · the Gateway's load balancer | $333.59<!--FD21--> | $9.83<!--FD22--> | $343.42<!--FD25--> |
| **C · Total** | `A + B` | $866.79<!--FD27--> | $10.76<!--FD28--> | **$877.54<!--FD29-->** |

**Right-sized** ᴱ — each line sized to its observed use. The variable
column is unchanged, as sizing doesn't influence NAT or cross-AZ traffic at rest.

| Block | Fixed | Variable at rest | Total |
| :--- | ---: | ---: | ---: |
| **B · Dedicated** | $410.39<!--FE8--> | $0.93<!--FD24--> ᴰ | **$411.31<!--FE9-->** |
| A · Shared | $316.60<!--FE7--> | $9.83<!--FD22--> ᴰ | $326.43<!--FE16--> |
| **C · Total** | $726.98<!--FE10--> | $10.76<!--FD28--> ᴰ | **$737.74<!--FE11-->** |

Errors found at rest weren't added to any table. They were $175.85<!--FD35-->/month: EKS control-plane
logs that nobody chose, $100.95<!--FD34-->, and an ArgoCD self-heal loop, $65.85<!--FD32--> in
cross-AZ traffic plus $9.05<!--FD33--> in T3 CPU credits. They all fixed or added to `tech-debt.md`. 

### 4.2 Marginal

The always-on minimum of the API and TEI (§2.3) belongs to the floor, so it is subtracted from
every run before any per-unit figure is computed.

#### Per 1M documents

For the calculation used single point – N=25, the sweet spot. One run processes the 100-document fixture for
$2.49<!--FD70-->, so if we multiply it 10,000 times, we got $24,875<!--FD37--> per 1M documents.
Every run started its worker nodes from zero, so the figure assumes documents arrive in batches
of 100. A continuous load would pay node start-up and image pulls once and cost less.

Every row is cash, what the account paid in the run's CUR hour (`01-ingestion` Notes, CUR table).
The chunker and indexer run alone on the `apps-compute` nodes, so their row is those whole nodes,
capacity no pod requested included. TEI grew from 2 to 4 replicas on nodes that were already
running.

| Component | $/1M docs | Share |
| :--- | :--- | :--- |
| Chunker and indexer, whole `apps-compute` nodes | $10,916<!--FD167--> ᴱ | 43.9<!--FD170-->% |
| NAT, SQS and S3 | $13,884<!--FD168--> ᴱ, NAT 99.6<!--FD173-->% of it | 55.8<!--FD171-->% |
| TEI above its always-on minimum | $75<!--FD169--> ᴱ | 0.3<!--FD172-->% |
| **Total** | $24,875<!--FD37--> ᴱ | 100% |

#### Per 1k queries at 1000 req/s, 24/7

Retrieval costs about $0.0008<!--FE18--> ᴱ per 1k queries, ~$2,077<!--FE19--> ᴱ a month: the nine
serving nodes that held 1000 req/s in r1000, $1.47<!--FM89-->/hour less the always-on pair the
floor already pays for, plus cross-AZ transfer at the campaign's rate per query, with image pulls
paid once instead of on every scale-out. Generation adds ~$0.51<!--FD39--> ᴱ per 1k,
~644<!--FD174-->× retrieval, so it is almost the whole marginal.

### 4.3 Amortization

The Block B floor is paid every month at any load. Each document or query has a share of it, and the
share shrinks as volume grows. The tables below show the cost of one unit and the floor's share of
it, both reducing with volume.

`Effective $/unit = ( Block B Floor + Marginal × V ) ÷ V`

V is the monthly volume. **Floor share** is the part of the effective cost that comes from the
Block B floor, $534.12<!--FD26-->/month as built. Each table carries all of it, so adding a `$/doc`
row to a `$/query` row counts the floor twice. This is arithmetic on §4.1 and §4.2, and no run
measured it.

#### Documents

Documents use the N=25 marginal, $24,875<!--FD37-->/1M docs = $0.02488<!--FD38-->/doc.

| Monthly documents | Effective $/doc ᴱ | Floor share |
| :--- | :--- | :--- |
| 1 000 | $0.5590<!--FD92--> | 95.6<!--FD96-->% |
| 10 000 | $0.0783<!--FD93--> | 68.2<!--FD97-->% |
| 100 000 | $0.0302<!--FD94--> | 17.7<!--FD98-->% |
| 1 000 000 | $0.0254<!--FD95--> | 2.1<!--FD99-->% |

Floor share falls below half at ~21,472<!--FD41--> documents a month.

#### Per-query marginal

Retrieval is priced from the nodes that held 1000 req/s, without the always-on minimum (§4.2), and
changes with the infrastructure. Generation is Bedrock's price per token.

| Marginal line | $/query | Share of the marginal |
| :--- | :--- | :--- |
| Retrieval — serving capacity above the always-on minimum | $0.00000079<!--FD100--> ᴱ | 0.2<!--FD159-->% |
| Generation — Bedrock | $0.000509<!--FD118--> ᴱ | 99.8<!--FD160-->% |
| **Per-query marginal** | **$0.000509<!--FD158--> ᴱ** | 100% |

#### Queries

According to the fact that generation is 99.8% of the marginal, decided to build additional table, that shows
difference of floor share for amount of total queries per month, it's mostly Bedrock's token price plus the floor.

![Effective cost per query and floor share against monthly query volume, log scale](charts/amortization-queries.svg)

| Monthly queries | Effective $/query ᴱ | Floor share |
| :--- | :--- | :--- |
| 10 000 | $0.0539<!--FD101--> | 99.1<!--FD105-->% |
| 100 000 | $0.00585<!--FD102--> | 91.3<!--FD106-->% |
| 1 000 000 | $0.00104<!--FD103--> | 51.2<!--FD107-->% |
| 10 000 000 | $0.000563<!--FD104--> | 9.5<!--FD108-->% |
| 500 000 000 | $0.000510<!--FD139--> | 0.2<!--FD141-->% |
| 1 000 000 000 | $0.000510<!--FD140--> | 0.1<!--FD142-->% |

Floor share falls below half at ~1,048,470<!--FD43--> queries a month, ~0.4<!--FD143--> req/s
sustained. Above that, most of the effective cost is the token price.

Retrieval is 0.2<!--FD159-->% of the marginal. It contains the API and TEI replicas above the
always-on minimum, which could require more nodes for them. Price and share used at 1000 req/s, which are about
2,628,000,000<!--FD116--> queries a month. Every row in the table, that below volume – needs
fewer replicas, so its retrieval figure is less accurate.

### 4.4 Declined trade-offs

#### Fargate instead of EC2 Spot nodes for ingestion

Comparing Fargate at N=25, the ingestion pool's EC2 Spot nodes billed $0.8594<!--FM93--> for this
run, instances alone. The worker pods requested $0.2595<!--FD122--> of it, which was 30<!--FD176-->%,
and $0.5784<!--FM94-->, 67<!--FD177-->%, was capacity no pod requested. Fargate bills per pod,
so the same pod-hours cost $0.7562<!--FD121--> at its on-demand rates, which is 0.88<!--FD161-->× the Spot nodes.
It also removes node provisioning and Spot interruptions, but in exchange, it downloads the image once per task,
and each Job is a task, while node downloads each image once per node and caches it.

The n25 run created 58<!--FM83--> jobs, so technically fargate would pull images 3-6 times more times, but Fargate
skips node bootstrap. But with instances that match the pods, sized the way §4.1 sizes the floor, Fargate loses: the
same run on `m7g.xlarge` would cost about $0.55<!--FE20--> ᴱ, so Fargate would cost
1.4<!--FE21--> ᴱ times more, though it stays a reasonable option.

#### VPC endpoint instead of the NAT gateway, query path

Every Bedrock call leaves the VPC through the NAT gateway, which charges $0.052<!--FR4--> per GB
it processes. An interface VPC endpoint charges $0.01<!--FR15-->/GB, but it also costs
$26.28<!--FD48-->/month for its three ENIs, one per AZ, whether or not any traffic passes.

The endpoint pays back once the per-GB saving covers that fixed fee, at 625.71<!--FD49--> GB a
month. One query moves ~11.4 KB ᴱ through the NAT (`02-inference/K4`), so the crossover is
~54,854,311<!--FD50--> ᴱ queries a month, about 21 req/s ᴱ sustained. At the reference volume of
1,000,000<!--FE14--> queries the NAT costs $0.59<!--FD53--> ᴱ a month, 0.12<!--FD55-->% of
generation, and the crossover sits 55× above it.

However, besides the cost, the endpoint reaches Bedrock in `eu-central-1` only, and the current
model is served only in US regions. So such change would also require to change a model to one,
that in `eu-central-1` first.

## 5. Guardrails

### 5.1 Memory limits

Peak is each pod's highest `container_memory_working_set_bytes` in the window, the value the kubelet compares
with the limit before an OOM kill (`01-ingestion/M7` · `02-inference/Q8`).

| Component | Keep | Peak working set | Limit ÷ peak | Enforced in | Comment |
| :--- | :--- | ---: | ---: | :--- | :--- |
| Chunker | `1Gi` | 445<!--FM79--> MiB (N=25) | 2.30<!--FD156-->× | `deploy/k8s/apps/chunker` | The margin is deliberate, well past `peak+30%`: the full corpus holds a 124 MB file against the fixture's 78.8 MB, and an image-heavy PDF decodes to several times its file size |
| Indexer | `4Gi` | 2,219<!--FM80--> MiB (N=75) | 1.85<!--FD157-->× | `deploy/k8s/apps/indexer` | Raise `requests.memory` to `2560Mi`: at 2,048<!--FR37--> MiB it sits below the peak, so §2.3's packing density overstates the real one. At 2560Mi fewer indexers fit a node, and the effect on `$/1M docs` is unmeasured |
| Go API | `512Mi` | 165<!--FM76--> MiB (r500) | 3.10<!--FD154-->× | `deploy/k8s/apps/api` | Sized for one replica carrying the whole rate: a pinned replica reached 439<!--FM77--> MiB, 86% of the limit, a state reachable at scale-in and under imbalanced routing |
| TEI | `1Gi` | 670<!--FM78--> MiB (r050) | 1.53<!--FD155-->× | `deploy/k8s/apps/tei` | Memory decides nothing here: at `requests.cpu: 3000m` packing is CPU-bound, so the 768<!--FR34--> MiB request does not affect density |

### 5.2 Max replicas

All three settings are max replicas. On the ingestion path
the ScaledJob setting is the axis itself, and TEI peaked at 26 of its 30 replicas. On the query path
the pool's CPU limit was reached before TEI's max: at r1000 TEI ran on 11 pods (§2.3).

| Setting | Keep | Observed | Enforced in | Comment |
| :--- | :--- | :--- | :--- | :--- |
| Ingestion concurrency, both ScaledJobs | `maxReplicaCount: 20` ᴱ | chunker never above ~20 at any N. The N=25 sweet spot held a time-weighted mean of 19.5 | `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml`, committed 2026-09-19, applies at the next cluster bootstrap | No point separates 20 from 25, it based on estimate |
| Go API replicas | `maxReplicaCount: 10` | 6 at r1000 | `api-scaler` | Sufficiency above 1000 req/s\* is untested |
| TEI replicas | `maxReplicaCount: 30` | 11 at r1000, 6 cores each | `tei-embeddings-scaler` | The serving pool's CPU limit stops TEI first. 11 pods held 1000 req/s\* (§2.3) |

The `apps-serving` NodePool keeps `limits: cpu: 100`, during testing reached it at r1000 and at N=125, and it
was enough for both.

### 5.3 Alerts, topology and spend

- **Karpenter node consolidation delay — keep `consolidateAfter: 5m` under `WhenEmpty`, and do not lower it for cost**

Karpenter by default has configured with `0s` under `WhenEmptyOrUnderutilized` and for this setup a node would be empty
for a moment between Job started. Karpenter reads it as idle and removes a node the next pod was about to use. A
`5m` delay would fix that consolidation issue, so better to not reduce.

- **Serving pool full — alert when `tei-embeddings` pods stay Pending, or `apps-serving` reaches its `cpu: 100` limit**
  §3.2 · §2.3 → `prometheus/rules.yaml`

At r1000 the pool set at its limit and TEI could not grow past 11 pods(applicable for tei `cpu 6 / 8`).
The response is a higher NodePool limit and, past 256 vCPU, more Spot vCPU quota.

- **Budget alarm — $1,032.84<!--FD56--> ᴱ/month**

Right-sized Block C, $737.74<!--FE11--> ᴱ, × 1.4 for headroom. However, Block B is the better base, but scoping
a budget to it needs a block tag or cost category(`docs/tech-debt.md` #13).
