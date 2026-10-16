<!-- PROVENANCE. Read this before editing.

This file is the source of the published article. It is a derived document, not a copy:
`report.md` stays the authority on every claim, and this file is allowed to compress,
reorder and drop — never to assert anything `report.md` does not.

Numbers. Every figure here carries the same hidden mark as in `report.md` - the ref glued to
the digits, the form is in `docs/report/formats.md` - because `figures.yaml` is the one
registry and this file is in its `scan`. A figure that changes moves both documents or fails `report-kit figures check`.
Nothing is typed by hand from the report, and nothing is computed in prose.

Publication. `docs/report/scripts/render_article.py` strips the marks into `rendered/article.md`,
puts links to Part 1 and to `report.md` on GitHub under the title, rewrites repo-relative
pointers into links to `master`, and stamps the sha it rendered from. It refuses to run while the figure check is dirty. The published text is
always that render, never this file and never a paste from `report.md`.

What is kept, compressed and dropped follows the rule in `AGENTS.md` §7. Charts come from `charts/*.csv` through `report-kit charts`; the article and the
slide deck are where they are used.

Source: `report.md` · registry: `figures.yaml` · rule: `AGENTS.md` §7
-->

# Executive Engineering Report — simple-rag

This report measures cost and performance on both flows of a RAG system: asynchronous document
ingestion and synchronous queries. It also shows what the system costs at rest and how that cost
spreads over volume.

- **Report** — `simple-rag` · v1.0 · 2026-10-14
- **System under test** — chunker `sha-404a267` · indexer `sha-32365dc` · api `sha-bafdc1f` · tei
  `cpu-1.6` · commit `1ef1f0a8`, 2026-09-05. TEI ran at `cpu 6 / 8` for r1000 only, `3 / 4`
  everywhere else (§3.2)
- **Scope** — text-layer PDF corpus, bulk drop · N ≤ 125 concurrent ingestion pods · R ≤ 1000 req/s
  · EKS + Karpenter, KEDA (serving from 2 replicas, ingestion from zero), self-hosted Qdrant, TEI
  `bge-small-en-v1.5` · `eu-central-1`
- **Cost source** — AWS Cost and Usage Report 2.0 · USD · method in the
  [repository](https://github.com/maksimillian1/simple-rag)
- **Figures** — measured unless marked: ᴰ derived · ᴿ recorded · ᴱ estimated

---

## Coverage

**Covered**

- Ingestion throughput, cost per run and cost per 1k documents ᴱ (§3.1)
- Per-component share of ingestion cost (§4.2)
- TEI cost caused by ingestion (§3.1, §4.2)
- Ingestion constraint (§3.1)
- Sustained query rate, the replicas it required and the query flow constraint (§3.2)
- Retrieval cost per 1k queries at 1000 req/s ᴱ (§4.2)
- Generation cost per 1k queries, Bedrock ᴱ (§4.2)
- Idle floor, split A / B / C, as built and right-sized ᴱ (§4.1)
- Errors found at rest, excluded from the floor (§4.1)
- Amortization across volumes, documents ᴱ (§4.3)
- Amortization across volumes, queries, generation included ᴱ (§4.3)
- Fargate against EC2 Spot nodes, ingestion ᴱ (§4.4)
- Warm-up and consolidation-tail share, partly: NAT, SQS and S3, almost all of it image pulls while
  nodes start, are 55.8<!--FD171-->% of the N=25 run (§4.2). Node boot and teardown time itself was
  not measured

**Out of scope**

- Next ingestion bottleneck after the indexer fix: what limits throughput once the indexer processes
  documents in parallel, TEI or Qdrant writes. Their metrics were not collected. TEI's serving pool
  already touched its 100 vCPU limit at N=125 (§5.2)
- Ingest and query contention on shared Qdrant and TEI: how query latency and errors change while
  ingestion runs in parallel
- Scaler tuning, thresholds and cooldowns: how much of convergence time is configuration rather than
  node provisioning
- Query tail latency, p99: how slow the slowest 1% of queries get
- Retrieval quality against quantization: what INT8 compression costs in recall. INT8 SQ is a frozen
  given here
- Behaviour above the sustained rate: whether overload degrades or collapses the deployment
- End-to-end latency including Bedrock generation: what a user waits for once Bedrock answers
- Reliability economics, Spot interruption under load: the price of the resilience mechanism, work
  lost, duplicates, recovery time

---

## 1. BLUF

- **Ingestion flow** — $24.88<!--FD37--> ᴱ per 1k docs at N=25, the cheapest point. The highest
  tested concurrency, N=125, reached 2.60 docs/min at $88.16<!--FD72--> ᴱ per 1k docs. Throughput is
  limited by code: each indexer pod sends one TEI call at a time, so rewriting that loop would give
  much more than adding extra pods (§3.1)
- **Query flow** — ~$0.51<!--FD179--> ᴱ per 1k queries, 99.8<!--FD160-->% of it Bedrock generation.
  The highest tested rate, 1000 req/s, filled the serving pool to its 100<!--FR38--> vCPU limit, and
  Qdrant, at 78<!--FD137-->% of its CPU, is the next ceiling. Without generation, a query returns in
  ~40-60 ms at p95 (§3.2, §4.2)
- **Idle floor, Block B** — $534.12<!--FD26--> / month (Block C $877.54<!--FD29-->), what the
  feature costs while idle

**Verdict** — **ship with guardrails.** Nothing blocks release. Both flows held the volumes tested,
but the query flow has no headroom above 1000 req/s until the serving pool's CPU limit rises
(§5.2). Every guardrail in §5 is implemented or declared.

---

## 2. Test Setup & Scope

### 2.1 Configuration freeze and metric sources

Every run used one configuration, frozen before the first run.

- **Always-on replicas** — API 2 and TEI 2. They are the serving part of the floor (§4.1)
- **Autoscaling triggers** — KEDA on CPU per replica: API at 0.2 cores, TEI at 1.5
- **TEI pod size** — `cpu 3 / 4`, and `6 / 8` at r1000 only, so r1000's numbers hold for `6 / 8`
- **Serving pool** — `apps-serving` NodePool, Spot and On-Demand, with a `cpu: 100` limit. The
  query flow reached that limit at 1000 req/s (§3.2)
- **Ingestion pool** — `c7g` Spot in `xlarge`–`4xlarge`
- **Shared TEI** — one deployment serves both flows. Ingestion is charged only for TEI above the
  always-on minimum (§4.2)
- **Qdrant** — 2 × `r7g.large`, one shard held by both, INT8 SQ
- **Generation** — the chosen LLM is `llama3-1-8b`

### 2.2 Ingestion flow — per document

- **Unit of work** — one source document, complete when its last chunk is upserted and counted in
  Qdrant `points_count`
- **Workload fixture** — 100 files, 1.38GB, bulk drop · median 8.77MB, p95 49.23MB · frozen at
  commit `bafdc1f` (2026-08-31)
- **Denominator** — 100 documents (files), frozen with the fixture. The same corpus is freshly
  ingested at every point, confirmed by an identical 84,018-chunk `points_count` at every point
- **Window** — opens at the first `s3:ObjectCreated` and closes when the ingestion pool reaches zero
  nodes and TEI returns to its always-on minimum, plus five minutes. Upload is started by a script
  that uploads local files to S3

### 2.3 Query flow — per query

- **Unit of work** — one search request, complete when the retrieved context is written to the
  response. Generation in Bedrock is outside the unit
- **Workload fixture** — 5 query options (`docs/report/scripts/load.js:57-63`), one picked at random
  per request and sent at a constant rate
- **Collection** — Qdrant loaded from the `01-ingestion` snapshot: 84,018 chunks, unchanged across runs
- **Denominator** — queries served inside each run
- **Window** — the whole generator run. It opens with both deployments at their always-on minimum,
  so it includes the scale-out
- **Run names** — `rN` is the run offered N req/s, as in r1000

---

## 3. Efficiency Frontier

### 3.1 Ingestion flow — throughput, cost and constraint

Tested at N = 10, 25, 50, 75 and 125. N=25 was the nearest to the sweet spot, the cheapest operating
point at $24.88<!--FD75--> ᴱ per 1k docs. Throughput is limited by the indexer's code, not by any
resource.

N is the max replicas setting (`maxReplicaCount`) on both ScaledJobs. It is a limit on concurrent
pods, not observed concurrency. The indexer ran at max replicas at every point (125 of 125 at
N=125). The `chunker` peaked at ~20 whatever the N, technically because the 100-file corpus was the
same.

Cost per document is V-shaped, the cheapest at N=25, and the neighboring points on both sides are
higher.
N=10 costs $44.71<!--FD76--> ᴱ per 1k docs against $24.88<!--FD75--> ᴱ at N=25, because it runs twice
as long (132.5 min against 61.7 min) while fixed per-hour costs keep billing.

Throughput rises at every step and never levels off. Per step, it gains +113%, +40%, +2.6%, then
+11.6%. If speed matters, stop at N=50: it buys +40% docs/min over N=25 for $19.46<!--FD77--> ᴱ more
per 1k docs.

Ingestion is limited only by how the indexer calls TEI, not by any resource. No worker reached its
CPU or memory limit at any N. Each indexer pod sends one TEI request at a time and waits for the
answer before sending the next (`apps/indexer/src/main.py`). Its throughput depends mostly on how
long that call takes, so the only way to go faster today is more pods.

**Time** by N:

- N=10 — 132.5 min
- N=25 — 61.7 min
- N=50 — 44.0 min
- N=75 — 42.9 min
- N=125 — 38.5 min

[IMAGE: charts/tradeoff-jobs.png — caption: Cost per 1k docs against throughput in docs/min, one point per N]

### 3.2 Query flow — sustained rate, latency and bottleneck

Tested at 50, 200, 300, 500 and 1000 req/s. The query flow held 1000 req/s for 1m45s at r1000
(14:57:16–14:59:01Z). No component saturated, but the serving pool hit its 100<!--FM92--> vCPU
limit, so TEI ran on 11<!--FM90--> pods of 6 cores (CloudTrail). That was enough: errors were high
while TEI was still scaling out, and dropped to 0.02<!--FM62-->% once the 11 pods were up.

r500 and r1000 have on average 0.78% and 4.97% errors over the whole run. Most of them came during
scale-out, while TEI was still adding replicas. After the replicas caught up, errors settled at
0.49<!--FM70-->% and 0.28<!--FM64-->%, close to r200 and r300 (0.24% and 0.20%). That residual is not
explained by scale-out, and its cause is not confirmed. Part of the requests were not sent: k6
skipped 10.7<!--FD145-->% and 5.2<!--FD144-->% of them during scale-out
([dropped iterations](https://grafana.com/docs/k6/v2.2.x/using-k6/scenarios/concepts/dropped-iterations/)),
and at r1000 it stopped sending for three minutes. Skipped requests lower the served rate but do
not count as errors.

Without generation, a query returns in ~40-60ms at p95. Every request has a fixed 2000ms stub
instead of the Bedrock call, and k6 measured 2.04s at r050 and 2.06s at r300 from outside the VPC.
There are two p95 readings. Envoy's is interpolated between its 1000 and 2500ms buckets, so it
reads 2425ms at every converged point, 300-400ms above k6. k6 is exact per request but reports one
figure per run, so at r500 and r1000 it includes the scale-out minutes.

Qdrant was the closest to saturation: it peaked at 1.568<!--FM59--> of 2<!--FR27--> cores. TEI
touched 97.5% of its CPU limit in r1000 while it was still scaling out, and the added replicas
relieved it. `api` peaked at 0.268 of 0.5 cores. r1000 is the only run where TEI ran with more CPU,
`6 / 8` cores instead of `3 / 4`, so its cost is not part of the same trend as the other runs.

[IMAGE: charts/frontier-api.png — caption: Envoy p95 latency (whole run and once scaled out) and API and TEI replicas against offered req/s, with the 2000 ms generation stub marked]

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
list rates. Described in two versions, As built and Right-sized, as after the analysis we can
choose the correct node sizes and exclude errors.

- **B · Dedicated** — Qdrant node + gp3 (current-gen PVC) · serving pool at 2+2 replicas · Bedrock
  interface endpoints (removed in the right-sized version, `ADR-0018`) · S3 at rest · SQS polling
- **A · Shared** — EKS control plane · core node group · Karpenter on Fargate · NAT hourly ·
  monitoring stack · the Gateway's load balancer
- **C · Total** — `A + B`

[IMAGE: charts/floor-blocks.png — caption: Monthly floor of Block B and Block A, as built against right-sized]

As built, Block B costs $534.12<!--FD26--> a month and Block C $877.54<!--FD29-->. Right-sized,
they cost $411.31<!--FE9--> ᴱ and $737.74<!--FE11--> ᴱ.

Right-sized ᴱ means each line is sized to its observed use. Variable cost at rest is unchanged,
because sizing doesn't influence NAT or cross-AZ traffic at rest.

Errors found at rest are not included in these figures. They were $175.85<!--FD35-->/month: EKS
control-plane logs that nobody chose, $100.95<!--FD34-->, and an ArgoCD self-heal loop,
$65.85<!--FD32--> in cross-AZ traffic plus $9.05<!--FD33--> in T3 CPU credits. They are all fixed or
recorded as tech debt.

### 4.2 Marginal

The always-on minimum of the API and TEI (§2.1) belongs to the floor, so it is subtracted from every
run before any per-unit figure is computed.

### Per 1k documents

The calculation uses a single point, N=25, the sweet spot. One run processes the 100-document
fixture for $2.49<!--FD70-->, so multiplying it by 10 gives $24.88<!--FD37--> per 1k documents.
Every run started its worker nodes from zero, so the figure assumes documents arrive in batches of
100. A continuous load would pay for node start-up and image pulls once and cost less.

Every figure here is cash, what the account paid in the run's CUR hour. The chunker and indexer run
alone on the `apps-compute` nodes, so their cost is those whole nodes, including capacity no pod
requested. TEI grew from 2 to 4 replicas on nodes that were already running.

NAT, SQS and S3 are $13.88<!--FD168--> ᴱ(55.8<!--FD171-->% of the cost, almost all of it NAT for image pulls while nodes
start). The worker nodes are $10.92<!--FD167--> ᴱ(43.9<!--FD170-->%), and TEI $0.07<!--FD169--> ᴱ(0.3<!--FD172-->%).

### Per 1k queries at 1000 req/s, 24/7

Retrieval costs about $0.0008<!--FE18--> ᴱ per 1k queries, ~$2,077<!--FE19--> ᴱ a month. That is the
nine serving nodes that held 1000 req/s in r1000, $1.47<!--FM89-->/hour, less the always-on pair
the floor already pays for, plus cross-AZ transfer at the campaign's rate per query, with image
pulls paid once instead of on every scale-out. Generation adds ~$0.51<!--FD39--> ᴱ per 1k,
~644<!--FD174-->× retrieval, so it is almost the whole marginal.

### 4.3 Amortization

The Block B floor is paid every month at any load. Each document or query has a share of it, and
the share shrinks as volume grows. The figures below show the cost of one unit and the floor's
share of it, both falling with volume.

`Effective $/unit = ( Block B Floor + Marginal × V ) ÷ V`

V is the monthly volume. **Floor share** is the part of the effective cost that comes from the
Block B floor, $534.12<!--FD26-->/month as built. The documents figures and the queries figures each
carry all of it, so adding a `$/doc` figure to a `$/query` figure counts the floor twice. This is
arithmetic on §4.1 and §4.2, and no run measured it.

### Documents

Documents use the N=25 marginal, $24.88<!--FD37-->/1k docs = $0.02488<!--FD38-->/doc.

* **1,000 documents/month:** floor share is 95.6<!--FD96-->% ($0.5590<!--FD92-->/doc)
* **10,000 documents/month:** floor share is 68.2<!--FD97-->% ($0.0783<!--FD93-->/doc)
* **100,000 documents/month:** floor share is 17.7<!--FD98-->% ($0.0302<!--FD94-->/doc)
* **1,000,000 documents/month:** floor share is 2.1<!--FD99-->% ($0.0254<!--FD95-->/doc)

### Queries

According to the fact that generation is 99.8<!--FD160-->% of the marginal, decided to build an additional chart
that shows the difference in floor share for the total number of queries per month. The cost is
mostly Bedrock's token price plus the floor.

[IMAGE: charts/amortization-queries.png — caption: Effective cost per query and floor share against monthly query volume, log scale]

Floor share falls below half at ~1.05<!--FD180--> million queries a month, ~0.4<!--FD143--> req/s
sustained. Above that, most of the effective cost is the token price.

Retrieval is 0.2<!--FD159-->% of the marginal. It covers the API and TEI replicas above the
always-on minimum, which could require more nodes for them. The price and share are taken at
1000 req/s, which is about 2,628,000,000<!--FD116--> queries a month. Every volume below that needs
fewer replicas, so its retrieval figure is less accurate.

### 4.4 Declined trade-offs

### Fargate instead of EC2 Spot nodes for ingestion

Comparing Fargate at N=25, the ingestion pool's EC2 Spot nodes billed $0.8594<!--FM93--> for
this run, instances alone. The worker pods requested $0.2595<!--FD122--> of it, which was
30<!--FD176-->%, and $0.5784<!--FM94-->, 67<!--FD177-->%, was capacity no pod requested. Fargate
bills per pod, so the same pod-hours cost $0.7562<!--FD121--> at its on-demand rates, which is
0.88<!--FD161-->× the Spot nodes. It also removes node provisioning and Spot interruptions. In
exchange, it downloads the image once per task, and each Job is a task, while a node downloads each
image once per node and caches it.

The N=25 run created 58<!--FM83--> jobs, so technically Fargate would pull images 3-6 times more often, but
Fargate skips node bootstrap. But with instances that match the pods, sized the way §4.1 sizes the
floor, Fargate loses: the same run on `m7g.xlarge` would cost about $0.55<!--FE20--> ᴱ, so Fargate
would cost 1.4<!--FE21--> ᴱ times more, though it stays a reasonable option.

### VPC endpoint instead of the NAT gateway, query flow

Every Bedrock call leaves the VPC through the NAT gateway, which charges $0.052<!--FR4--> per GB it
processes. An interface VPC endpoint charges $0.01<!--FR15-->/GB, but it also costs
$26.28<!--FD48-->/month for its three ENIs, one per AZ, whether or not any traffic passes.

The endpoint pays back once the per-GB saving covers that fixed fee, at 625.71<!--FD49--> GB a
month. One query moves ~11.4 KB ᴱ through the NAT, so the crossover is ~55<!--FD181--> ᴱ million
queries a month, about 21 req/s ᴱ sustained. At the reference volume of 1,000,000<!--FE14-->
queries the NAT costs $0.59<!--FD53--> ᴱ a month, 0.12<!--FD55-->% of generation, and the crossover
sits 55× above it.

Besides the cost, the endpoint reaches Bedrock in `eu-central-1` only, and the current model is
served only in US regions. So such a change would also require changing a model to one that is in
`eu-central-1` first.

---

## 5. Guardrails

### 5.1 Memory limits

Peak is each pod's highest `container_memory_working_set_bytes` in the window, the value the kubelet
compares with the limit before an OOM kill.

- **Chunker** — 1Gi limit, 445<!--FM79--> MiB peak, 2.30<!--FD156-->× headroom,
  real documents can be larger than the fixture
- **Indexer** — 4Gi limit, 2,219<!--FM80--> MiB peak, 1.85<!--FD157-->×. The memory request is raised
  from 2,048<!--FR37--> MiB to 2560Mi.
- **Go API** — 512Mi limit, 165<!--FM76--> MiB peak, 3.10<!--FD154-->×. replica reached 439<!--FM77--> MiB.
- **TEI** — 1Gi limit, 670<!--FM78--> MiB peak, 1.53<!--FD155-->×. CPU decides packing, so memory
  does not affect density.

### 5.2 Max replicas

All three settings are max replicas. In the ingestion flow the ScaledJob setting is the axis itself,
and TEI peaked at 26 of its 30 replicas. In the query flow the pool's CPU limit was reached before
TEI's max: at r1000 TEI ran on 11 pods (§3.2).

- **Ingestion concurrency** — `maxReplicaCount: 20` on both ScaledJobs ᴱ. The chunker never ran
  above ~20, and no point separates 20 from 25.
- **Go API** — max 10 replicas, 6 used at 1000 req/s. Above 1000 req/s it is untested.
- **TEI** — max 30 replicas, but the serving pool's limit stops it first: 11 pods of 6 cores held
  1000 req/s.
- **Serving pool** — `cpu: 100` limit, reached at r1000 and at N=125, and enough for both.

### 5.3 Alerts, topology and spend

- **Karpenter node consolidation delay — keep `consolidateAfter: 5m` under `WhenEmpty`, and do not
  lower it for cost**

By default, Karpenter is configured with `0s` under `WhenEmptyOrUnderutilized`, and in this setup a
node would be empty for a moment between Jobs starting. Karpenter reads it as idle and removes a node the
next pod was about to use. A `5m` delay would fix that consolidation issue, so it is better not to
reduce it.

- **Serving pool full — alert when `tei-embeddings` pods stay Pending, or `apps-serving` reaches its
  `cpu: 100` limit** (§3.2)

At r1000 the pool sat at its limit, and TEI could not grow past 11 pods (with TEI at `cpu 6 / 8`).
The response is a higher NodePool limit and, past 256 vCPU, more Spot vCPU quota.

- **Budget alarm — $1,032.84<!--FD56--> ᴱ/month** (§4.1)

Right-sized Block C, $737.74<!--FE11--> ᴱ, × 1.4 for headroom. However, Block B is the better
base, but scoping a budget to it needs a block tag or cost category.
