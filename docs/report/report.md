# Executive Engineering Report — simple-rag

What the ingestion and inference paths of a RAG feature actually cost, and where adding
concurrency stops buying throughput.

| | |
| :--- | :--- |
| Report | `simple-rag` · v1.0 |
| Application under test | image digests: api `⟨sha256:…⟩` · chunker `⟨…⟩` · indexer `⟨…⟩` |
| Price basis | region `⟨fill⟩` · AWS public price list retrieved `⟨date⟩` |
| Runs | E1 ingestion sweep · E2 24h idle window · E4 query load |
| Raw data | `docs/report/data/` |
| Supersedes | — |

> **Provenance:** every figure is measured unless marked.
> ᴬ arithmetic (price list × count) · ᴹᵒ modeled (extrapolated) · ᴱ estimated (judgement).

**Scope.** This report prices two paths of one feature: asynchronous document ingestion
and synchronous query serving. The Kubernetes platform they run on exists for other
workloads too; §4.1 separates what belongs to the feature from what is shared, and
prices both.

---

## Open decisions — delete this block before publishing

| # | Decision | Blocks |
| :--- | :--- | :--- |
| D1 | Region and price basis | all of §4 |
| D2 | Second unit of work (per page) — yes / no | §2.1, §3.1, §4.2 |
| D3 | Number of features assumed to share the platform, for the allocation row | §4.1 block A |
| D4 | Does E4 include the concurrent ingest + query point | §3.6 |

Placeholders are written `⟨like this⟩`. None may remain in the published version.

---

## 1. BLUF

*Conclusion first, evidence after. Written **last**, from finished numbers — an executive
reads the first thirty seconds and stops.*

Rule for this table: an absolute number decides nothing. Every row carries a reference
value it is compared against, and a plain sentence saying what it means.

| Metric | Result | Reference | What it means |
| :--- | :--- | :--- | :--- |
| Ingestion cost at the optimum | ⟨§4.2⟩ | vs ⟨§4.4 Fargate⟩ | what one million documents cost to ingest, and whether the Spot approach beat the serverless one |
| Feature idle floor | ⟨§4.1 block B⟩ /mo | vs ⟨§4.1 block C⟩ standalone | what this feature burns on a weekend with zero traffic, on top of a platform that already exists |
| Peak stable ingest rate | ⟨§3.1⟩ docs/min at N=⟨§3.3⟩ | plateau begins at N=⟨§3.3⟩ | past this concurrency you pay more and get nothing |
| Query SLO under load | p95 = ⟨§3.6⟩ ms at ⟨§3.6⟩ RPS | target < 200 ms | whether the latency promise made in article 1 survives real load |
| Primary constraint | ⟨§3.5⟩ | cost to remove: ⟨§3.5⟩ ᴬ | which component decides throughput, and the price of the next scaling step |

**Verdict:** ⟨one sentence naming one action⟩

---

## 2. Workload Contract & Envelope

*What was measured, on what input, and under which conditions the numbers hold. Without
this section every figure below is unfalsifiable — and a reader who cannot falsify a
number does not trust any of them.*

### 2.1 Unit of work

> **Yields:** the denominator of the entire report.
> **From:** definition, not measurement.
> **Before the run:** must fit in one unambiguous sentence, including the exact moment a
> unit counts as done.

Every cost figure here is `spend ÷ units of work`. The unit is chosen once and never
changes, because it is what makes the numbers comparable to anything at all. A total
monthly spend supports no decision; a cost per document supports several — pricing,
capacity planning, and the compute-mode comparison in §4.4.

**Ingestion unit:** ⟨one sentence — e.g. one PDF ingested end to end, counted when its
final chunk batch is committed to Qdrant⟩

**Query unit:** ⟨one sentence — e.g. one search request answered end to end⟩

**Open (D2):** the corpus is book-length PDFs with a wide page distribution, so a
per-document figure is partly a property of the fixture rather than of the architecture.
A per-page figure transfers to a different corpus and costs nothing extra to compute from
the same run. Decide whether the report carries one denominator or two.

### 2.2 Workload fixture

> **Yields:** the input constant that makes the sweep points comparable, and the raw
> material of the Envelope.
> **From:** the profiling script, run once, output committed to
> `docs/report/data/corpus-profile.txt`.
> **Before the run:** profile first, then snapshot. A fixture that changes between points
> makes the run matrix meaningless.

| | |
| :--- | :--- |
| Source dataset | `zabiullah/pdf-books-collection` (HuggingFace) |
| Snapshot location | ⟨path or S3 prefix⟩ |
| File count | ⟨from script⟩ |
| Pages per file | median ⟨script⟩ · 95th percentile ⟨script⟩ · total ⟨script⟩ |
| Extracted characters | total ⟨script⟩ · median per file ⟨script⟩ |
| Total bytes | ⟨script⟩ |

*How to read this: the median is the typical file — half the corpus is shorter. The 95th
percentile is the tail; five percent of files are longer, and they drive worst-case
memory and parse time. Both are printed by the script — copy them in verbatim.*

**Exact document count matters beyond description.** Because the corpus is frozen, the
number of documents is known precisely, which is what makes throughput computable from
wall-clock time alone in §3.1 — no per-worker instrumentation required.

**Ingest trigger:** the corpus is uploaded to the S3 raw bucket by a bulk upload script.
Upload is not part of the system under test — the measurement window opens at the first
`s3:ObjectCreated` event and closes when both SQS queues reach depth zero. Upload
duration and cost are excluded.

### 2.3 Envelope

> **Yields:** the boundary of every claim in the report. Without it the numbers silently
> overclaim.
> **From:** §2.2 profile plus the cluster configuration actually under test.
> **Before the run:** nothing. Written after §2.2, forward-looking, never as an apology
> and never as a closing "untested" list.

Fill this template from numbers already recorded above:

> These figures hold for **⟨corpus shape from §2.2 — e.g. text-layer PDFs, median ⟨n⟩
> pages⟩** ingested as a bulk drop, at **ingestion concurrency N ≤ ⟨max swept value⟩**,
> on **⟨cluster shape — e.g. EKS with Karpenter-managed Spot for ingestion, Qdrant
> self-hosted on dedicated On-Demand gp3 nodes, bge-small-en-v1.5 at 384 dimensions via a
> shared TEI service⟩**, in **⟨region⟩**. Outside these conditions, re-measure.

Then a short list of what is deliberately outside it, so nobody assumes coverage:
⟨e.g. scanned PDFs requiring OCR · GPU-backed embedding · corpora above ⟨n⟩ GB⟩.

### 2.4 Frontier X axis

> **Yields:** the parameter swept in §3 — the report's main curve is a curve *of* this.
> **From:** definition.
> **Before the run:** it must be a knob that moves end-to-end throughput. A knob on a
> component that is not the constraint produces a flat curve, and E1 is spent for nothing.

**Ingestion axis (§3):** `N` = concurrency of the ingestion pipeline — KEDA
`maxReplicaCount`, swept over **N ∈ {4, 8, 12, 16, 20, 24}**. Six points. The upper values
exist to produce the rising branch of the cost curve and to shift the bottleneck far
enough that a second constraint tier becomes observable (§3.5).

Which ScaledJob the knob applies to — indexer only, or both stages together — follows from
the constraint hypothesis in §3.5 and must be fixed before the first point.

**Query axis (§3.6):** requests per second against the Go API. Separate run, separate
unit, separate curve. Inference and ingestion do not share a denominator and must not
share an axis.

### 2.5 Measurement architecture

> **Yields:** nothing on its own. It is the precondition of §3 and §4.
> **From:** live scrape state, checked by query — not by reading config.
> **Before the run:** every row returns data. A component that is not scraped cannot be
> named as the constraint, because an absent series looks exactly like an idle one.

| Source | Supplies | Feeds | Status |
| :--- | :--- | :--- | :--- |
| Wall clock over the frozen corpus | documents per minute, per point | §3.1 | trivially available |
| `keda_scaler_metrics_value` | SQS depth; its rate of change is the drain-rate signal over time | §3.1 | scraped |
| `kube_node_labels` by instance and capacity type | how many billable nodes existed at each moment → node-hours | §3.1, §3.4, §4.2 | scraped |
| cAdvisor / kube-state-metrics | worker CPU and peak RSS per component | §3.5, §5 | scraped |
| **Karpenter** | node lifecycle timestamps and Spot interruption events | §3.1 validity, §3.4 | **⟨hard blocker⟩** |
| **TEI** | `te_queue_size`, `te_request_inference_duration`, `te_batch_next_size` | §3.5 | **⟨hard blocker⟩** |
| **Qdrant** `/metrics` :6333 | write latency, RSS, `points_count` | §3.5, §3.6, §4.5 | **⟨hard blocker⟩** |
| Go API | request latency histogram | §3.6 | ⟨missing⟩ |
| AWS Cost Explorer, by tag | idle spend split by component | §4.1 | ⟨tags not activated⟩ |

**Why the three marked rows are hard blockers.** Throughput tells you *that* the system
stopped scaling; only per-component metrics tell you *what* stopped it. Without TEI and
Qdrant instrumentation §3.5 collapses to a single unproven guess, and the second tier —
the whole reason for sweeping six points instead of four — cannot be claimed at all.

**Deliberately not instrumented in v1.0: per-execution worker summaries.** Attributing
documents to individual worker executions would require a structured exit-summary line
from each worker plus log-derived metrics. It is not needed here: the corpus is frozen, so
document counts come from the fixture, and drain rate comes from queue depth. Spot
interruptions — the one thing that could distort a sweep point — are visible in Karpenter
events without touching application code. The pattern remains valuable and is deferred to
v2.0, where reliability economics requires knowing *why* an execution ended.

---

## 3. Efficiency Frontier

*This section answers one engineering question: **how do we configure it?** The axis is
concurrency, the horizon is a single run, and the person turning the knob is the engineer.*

*Its output is one number that §4 consumes — marginal cost per unit at the best setting —
plus the concurrency ceiling that becomes a guardrail in §5.*

*The finding it exists to produce: throughput plateaus at one concurrency level, and unit
cost bottoms out at a **different**, usually lower one. Most engineers tune to the first
and never discover the second.*

### 3.1 Run matrix

> **Yields:** every other number in §3, and the marginal cost in §4.2.
> **From:** E1 — six runs over the frozen corpus.
> **Before the run:** identical image digests at every point; only the concurrency value
> changes. Between points, both SQS queues at depth zero and the ingestion NodePool at
> zero nodes — a warm node inherited from the previous point invalidates the comparison.

| N | Config commit | Docs/min | Wall time | Node-hours by type · spot/on-demand | $/run | $/1M docs | Saturation signal | Spot interruptions |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | | | |
| 8 | | | | | | | | |
| 12 | | | | | | | | |
| 16 | | | | | | | | |
| 20 | | | | | | | | |
| 24 | | | | | | | | |

**Config commit** — the sweep parameter lives in Git, so each point has its own commit.
That is expected and does not break the comparison; the application image digests in the
header are what must stay identical.

**Docs/min is measured twice, from independent sources.** Wall clock against the known
corpus size gives the point value; the derivative of SQS queue depth gives the shape over
time and catches a run that stalled and recovered rather than draining steadily. If the
two disagree by more than a few percent, the point is not trusted.

**$/run is computed, not billed.** AWS billing updates roughly daily and cannot see a
twenty-minute run at all:

```
$/run = Σ_instance_type ( node_count × duration_hours × price_per_hour )
```

Spot and On-Demand priced separately; node count over time comes from `kube_node_labels`
integrated across the run window.

**Saturation signal** — which component was at its ceiling when throughput stopped growing
at this point. One of: chunker CPU pinned · TEI request queue growing · Qdrant write
latency rising · queue not draining despite idle workers. This column is the raw material
of §3.5; an empty cell means that point contributes nothing to the constraint ladder.

**Spot interruptions** — count during the run, from Karpenter events. **Validity rule:**
a point with interruptions carries extra warm-up cost that belongs to no concurrency
level, and its `$/1M docs` cell is not comparable. Either re-run the point or mark the
figure ᴱ and exclude it from the curve fit. Do not average it in silently.

### 3.2 Chart — throughput and unit cost against concurrency

> **Yields:** the visual that carries §3.3.
> **From:** two columns of §3.1, nothing else.

One chart, dual Y axis, X axis = N:

- **Left axis:** docs/min (column 3). Expected shape — rises, then flattens.
- **Right axis:** $/1M docs (column 7). Expected shape — falls, reaches a minimum, rises
  again.

Plot script and generated image committed under `docs/report/charts/`.

### 3.3 Knee, sweet spot, and waste boundary

> **Yields:** the `maxReplicaCount` guardrail in §5.
> **From:** reading three points off §3.1 and §3.2.

| Point | How it is identified | N | Evidence from §3.1 |
| :--- | :--- | :--- | :--- |
| **Knee** | the last N where docs/min still rose meaningfully over the previous point — state the threshold used, e.g. under 10 % gain counts as flat | | |
| **Sweet spot** | the N with the lowest value in the `$/1M docs` column | | |
| **Waste boundary** | the first N where a step up raises `$/run` substantially while adding under 10 % throughput | | |

**Edge rule.** If the sweet spot lands on N=4 — the lowest point swept — it sits on the
boundary of the range and is not proven to be a minimum, because there is no descending
branch to its left. In that case add one point at N=1 or N=2 before claiming it. This is
a conditional seventh run, triggered by the result, not planned in advance.

**The gap between knee and sweet spot is the finding of this section.** State it as a
sentence: how much extra you pay per document to run at the knee instead of the sweet
spot, and how much throughput you give up going the other way. The guardrail is set at the
sweet spot; the knee is documented as the ceiling for a hurry.

### 3.4 Why unit cost rises again at high concurrency

> **Yields:** the mechanism behind the U-curve. Without it §3.3 is a chart with no
> explanation and the reader assumes noise.
> **From:** node lifecycle timestamps from Karpenter, per node, per run.
> **Before the run:** Karpenter scraped, or this section cannot be written.

Every node is billed from the moment it is provisioned, but produces work only after it
has booted, pulled the container image and initialised the runtime — roughly 60–90 seconds
in this system, to be confirmed. It is billed again for a short tail after the last
document, before consolidation removes it. Both windows produce zero units at full price.

At low N that overhead is spread across a long run and barely registers. At high N the
corpus drains fast, but there are many nodes each paying the same fixed warm-up and each
doing only a few minutes of real work. The overhead share of every billed node-hour grows,
and cost per document turns back up — even though wall-clock time keeps improving. That is
the entire mechanism of the U-curve.

Decompose node-hours at the lowest and highest N:

| N | Provisioning | Image pull | Init | Productive work | Consolidation tail | Overhead share |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | |
| 24 | | | | | | |

For scale-to-zero ephemeral workers this is the dominant cost effect and is almost never
quantified in published architectures.

### 3.5 Constraint ladder

> **Yields:** the constraint named in BLUF and the price of removing it.
> **From:** the saturation column of §3.1 plus per-component metrics, read at each point.
> **Before the run:** TEI and Qdrant scraped. Without them only one tier is claimable.

| Tier | Component | Proof metric and where it saturated | Relieved by | Cost to remove ᴬ |
| :--- | :--- | :--- | :--- | :--- |
| 1 | | | | |
| 2 | | | | |

**Why six points can prove a second tier.** A constraint ladder is the order in which
ceilings are hit. A tier counts as proven only when the previous one was actually relieved
and a new saturation was then observed — never because its numbers "looked close".

Sweeping concurrency relieves tiers on its own. If chunker CPU is the ceiling at N=4, then
at N=20 there are five times as many chunkers and that ceiling is gone; whatever saturates
instead — TEI queue depth, Qdrant write latency — is a genuinely proven Tier 2, observed
under relief rather than guessed. This is the reason the sweep runs to 24 rather than 16.

**No third tier is claimed**, regardless of what the numbers suggest. An unproven tier
weakens the tiers that were proven.

**Hypothesis recorded before the run.** The original design assumed the ceiling would be
TEI inference. On a book-length PDF corpus the likelier first ceiling is the Stage-1
chunker: PyMuPDF text extraction on a 300-page PDF is single-threaded CPU work and may
dominate embedding time by an order of magnitude. If the hypothesis inverts, the inversion
stays in the report — *"we expected to saturate inference and saturated PDF parsing
instead"* is what makes the measurement credible.

### 3.6 Query path

> **Yields:** the SLO row of BLUF, and whether ingestion load degrades query latency.
> **From:** E4 — load against the Go API at increasing RPS, plus one combined point.
> **Before the run:** Go API latency histogram and Qdrant metrics scraped.

| RPS | p50 | p95 | p99 | Qdrant search latency | Error rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| ⟨low⟩ | | | | | |
| ⟨mid⟩ | | | | | |
| ⟨high⟩ | | | | | |

**Combined-load point (D4).** One extra measurement: the mid RPS level run *while* an
ingestion point is active at the sweet-spot concurrency. This is the only measurement that
shows whether the two paths contend on Qdrant, and it costs roughly thirty minutes. Report
the p95 delta against the idle-cluster row above.

Article 1 claimed p95 under 200 ms. This table confirms that under load or replaces it.

---

## 4. Cost Structure

*This section answers a different question from §3: **should it be built this way at
all?** The axis is monthly business volume, the horizon is a year of ownership, and the
person turning the knob is the business, not the engineer.*

*The two sections are joined by one equation, the spine of the report:*

```
Monthly Cost = Floor + ( Marginal_per_unit × Volume )
                 ↑                 ↑
              §4.1              §3 supplies this coefficient, via §4.2
```

### 4.1 Floor — what it costs at zero load

> **Yields:** the idle-floor row of BLUF and the budget alarm in §5.
> **From:** E2 — a 24-hour window with zero traffic, spend pulled by tag at daily
> granularity. Lines Cost Explorer cannot resolve are computed from the price list and
> marked ᴬ.
> **Before the run:** cost allocation tags applied **and activated** in the billing
> console — activation is a separate step, applies going forward only, up to 24 hours of
> delay. During the window: no deploys, no config changes, no manual commands. ArgoCD
> reconciliation stays on; it is part of the floor.

For an asynchronous ingestion architecture the floor is where the entire value proposition
lives, so it is split rather than totalled.

**Block A — shared platform.** Exists whether or not this feature is deployed. Shown in
full for honesty, allocated for the BLUF.

| Line | Fixed / Variable | $/month | |
| :--- | :--- | :--- | :--- |
| EKS control plane | Fixed | | plan assumes ~$73 — verify |
| `core-on-demand` node group — CoreDNS, ArgoCD, Cilium, Prometheus, Grafana | Fixed | | |
| NAT Gateway — hourly charge plus per-GB processing | Fixed | | |
| EBS gp3 — Prometheus 10 Gi + Loki 10 Gi | Fixed | | |
| **Block A total** | | | |
| **Allocated share** ᴬ | | | Block A ÷ ⟨D3⟩ |

**Block B — feature-dedicated.** Disappears entirely if the RAG feature is removed.
**This is the number that goes to BLUF and drives §4.3.**

| Line | Fixed / Variable | $/month | |
| :--- | :--- | :--- | :--- |
| `database-on-demand` node group — Qdrant | Fixed | | |
| EBS gp3 — Qdrant volume | Fixed | | |
| TEI serving capacity at idle | ⟨fixed or scale-to-zero — confirm⟩ | | |
| VPC Interface Endpoints — Bedrock, SQS, S3, billed per AZ | Fixed | | |
| S3 storage — raw plus Glacier IR after 7 days | Variable with corpus size | | |
| SQS requests | Variable | | ~0 at idle |
| KEDA ScaledJob ingestion compute | Variable, floor = 0 | 0.00 | |
| **Block B total** | | | |

**Block C — standalone scenario.** `A + B`, one line: what this feature would cost as the
only workload on its own cluster. The number a greenfield reader needs, and the honest
counterweight to the allocated figure.

**Two notes this table exists for.**

The **NAT Gateway** is the hidden line of this architecture class and is missing from
almost every published version of it. Billed hourly regardless of traffic, and again per
gigabyte processed — including container image pulls and the indexer's model weight
downloads from HuggingFace.

Article 1 advertised **"$0.00 on idle."** This table states for exactly how many rows that
is true. A deepening of the claim with data in hand, not a retraction — which is the more
credible of the two positions.

### 4.2 Marginal — cost per unit at the sweet spot

> **Yields:** the coefficient in the spine equation.
> **From:** E1 at the sweet-spot N, decomposed by cost component.
> **Before the run:** components must sum to the total. Floor lines from §4.1 are excluded
> here by definition — mixing them inflates marginal cost and silently corrupts §4.4.

| Component | $/1M docs | Share |
| :--- | :--- | :--- |
| Stage-1 chunker compute | | |
| Stage-2 indexer compute | | |
| TEI serving compute attributable to ingestion | | |
| Warm-up and consolidation overhead (§3.4) | | |
| SQS requests | ᴬ | |
| S3 requests | ᴬ | |
| NAT data processing | | |
| **Total marginal** | | 100 % |

### 4.3 Amortization — where the floor stops dominating

> **Yields:** the lower bound of economic validity for this feature.
> **From:** arithmetic on §4.1 Block B and §4.2. No run required. Mark ᴬ.

This table is not a comparison against anything — it is an absolute curve. The floor is
paid every month whether one document is processed or a million. At low volume it is
divided among very few documents and the effective cost per document is absurd; at high
volume it vanishes into the marginal cost, which is the asymptote the curve approaches.

Block B is the right floor here: for a feature running on a cluster that exists anyway, the
question is what *this feature* costs to keep alive, not what the platform costs.

`Effective $/doc = ( Block B floor + Marginal_per_doc × V ) ÷ V`

| Monthly volume | Effective $/doc ᴬ | Floor share of total |
| :--- | :--- | :--- |
| 1 000 | | |
| 10 000 | | |
| 100 000 | | |
| 1 000 000 | | |

Close with one sentence: below the volume where floor share drops under half, you are
paying mostly for the feature to exist rather than for work done — that volume is the
lower bound of where this design makes economic sense.

### 4.4 Break-even — Karpenter Spot versus Fargate for the same Jobs

> **Yields:** the reference value for the BLUF cost row. An absolute cost figure supports
> no decision without one.
> **From:** arithmetic on measured E1 data against published Fargate pricing. No
> additional run.

The relevant alternative is not a different platform — the cluster exists regardless. It is
the compute mode for the same ingestion Jobs. Fargate removes node provisioning,
per-node image pull and Spot interruption handling entirely, and charges per vCPU-second
and GB-second at a premium over EC2 Spot.

The comparison is direct because §3.1 already measured what a run consumes:

| | Karpenter Spot (measured) | Fargate (arithmetic) |
| :--- | :--- | :--- |
| vCPU-hours per 1M docs | | same workload, same figure |
| GB-hours per 1M docs | | same workload, same figure |
| Warm-up overhead paid (§3.4) | | per-task cold start, no per-node image pull |
| Effective $/1M docs | | ᴬ |
| Interruption handling required | yes — SIGTERM path in the workers | no |
| Feature floor impact | 0 at idle | 0 at idle |

Output is one sentence of the shape: *"Spot is cheaper per million documents by X %, and
that discount is paid for with the interruption-handling code in the workers; below Y
documents per month the difference is smaller than the engineering cost of maintaining
it."*

### 4.5 Quality bought with cost — scalar quantization

> **Yields:** one guardrail and one line of §4.1 Block B. Included because this saving is
> purchased with retrieval accuracy, and an unpriced accuracy loss is not a saving.
> **From:** roughly 200 queries against both indexes locally, measuring top-10 result
> overlap. Ground truth is the system's own float32 index — no labelled dataset needed.
> **Before the run:** Qdrant RSS observable.

Framed as a money lever: RAM determines the instance class of the `database-on-demand`
node, a permanently billed line in the floor. Recall determines business risk. Not a
standalone ML benchmark; kept to one table.

| | float32 baseline | INT8 scalar quantization |
| :--- | :--- | :--- |
| Vector memory at 1M points, 384 dimensions | 1.536 GB ᴬ | 0.384 GB ᴬ |
| Qdrant RSS, measured | | |
| Smallest viable instance class | | |
| Resulting `database-on-demand` $/month | | |
| Top-10 overlap against baseline | 100 % by definition | |

Only the arithmetic row is defensible in advance. Article 1 claimed roughly 75 % RAM
reduction at under 1 % accuracy loss — this table confirms that on this corpus or replaces
it.

---

## 5. Guardrails

*A recommendation is prose and gets forgotten. A guardrail is a config value, sourced from
a number in this report, that can be committed to a file. The test: if it cannot be
committed, it does not belong in this table.*

> Rows whose source number does not exist after the runs are deleted, not left blank.

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Ingestion concurrency ceiling | `maxReplicaCount: ⟨§3.3 sweet spot⟩` | §3.3 | `deploy/k8s/.../scaledjob.yaml` |
| Indexer memory limit | `limits.memory: ⟨§3.5 peak RSS + 30 %⟩` | §3.5 | `deploy/k8s/apps/indexer/` — currently 2Gi |
| Chunker memory limit | `limits.memory: ⟨§3.5 peak RSS + 30 %⟩` | §3.5 | `deploy/k8s/apps/chunker/` |
| Max input file size | `MAX_ALLOWED_SIZE_BYTES: ⟨confirm 100 MB⟩` | §3.5 tail behaviour · ADR-0001 | `apps/chunker/` env |
| Chunks per SQS message | `⟨confirm 30⟩` | §4.2 SQS line · ADR-0004 | `apps/chunker/` env |
| Ingestion backlog alert | `⟨§3.1 drain rate × alert window⟩` | §3.1 | `prometheus/rules.yaml` |
| Query latency alert | `p95 > ⟨§3.6⟩ ms` | §3.6 | `prometheus/rules.yaml` |
| Budget alarm | `$⟨§4.1 Block B × 1.4⟩` | §4.1 | `terraform/budgets.tf` |

---

## Not covered in v1.0 — declared

*Stated rather than omitted silently, and phrased as scope, not apology.*

| Not included | What it would have supported | Why |
| :--- | :--- | :--- |
| Spot interruption injected under load | Reliability economics — cost of the resilience mechanism, recovery time, duplicate count | Idempotency via deterministic point IDs is designed in and verifiable by count comparison; pricing the mechanism needs its own run and its own instrumentation, deferred to v2.0 |
| Per-execution worker attribution | Documents and exit reason per worker execution | Not required for throughput, which comes from the frozen corpus and queue depth; needed only for the reliability run above |
| Third constraint tier | §3.5 | Two tiers are provable from this sweep; a third would be a guess and would weaken the two that are proven |
| Regression against a previous report | — | Unavailable at v1.0; becomes the strongest available section from v2.0 |
