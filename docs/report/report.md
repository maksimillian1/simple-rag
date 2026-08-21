# Executive Engineering Report — simple-rag

What asynchronous document ingestion actually costs, and where adding concurrency stops
buying throughput.

| | |
| :--- | :--- |
| Report | `simple-rag` · v1.0 |
| Application under test | image digests: chunker `⟨sha256:…⟩` · indexer `⟨…⟩` |
| Price basis | region `⟨fill⟩` · AWS public price list retrieved `⟨date⟩` |
| Runs | `sweep` — ingestion concurrency, 5 points · `idle` — 24h floor window |
| Raw data | `docs/report/data/` |
| Supersedes | — |

> **Provenance:** every figure is measured unless marked.
> ᴬ arithmetic (price list × count) · ᴹᵒ modeled (extrapolated) · ᴱ estimated (judgement).

**Scope.** This report prices one path of one feature: asynchronous document ingestion.
The synchronous query path is deliberately out of scope — it has its own frontier axis and
its own denominator, and mixing the two produces a number that supports no decision. The
Kubernetes platform both run on exists for other workloads too; §4.1 separates what
belongs to the feature from what is shared, and prices both.

---

## Open decisions — delete this block before publishing

| # | Decision | Blocks |
| :--- | :--- | :--- |
| D1 | Region and price basis | all of §4 |

*Closed:* per-page second denominator — **no**, one denominator. Platform allocation
divisor — **no**, Blocks A/B/C answer the question without an arbitrary divisor.
Combined ingest+query point — **no**, query path is out of scope.

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

**One denominator, not two.** A per-page figure would transfer better to a different
corpus, but it doubles every table in §3 and §4 for a conversion the reader can perform
themselves: the page distribution is printed in §2.2.

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
`s3:ObjectCreated` event and closes when the ingestion NodePool reaches zero nodes plus a
five-minute buffer. Upload duration and cost are excluded.

### 2.3 Envelope

> **Yields:** the boundary of every claim in the report. Without it the numbers silently
> overclaim.
> **From:** §2.2 profile plus the frozen configuration actually under test.
> **Before the run:** nothing. Written after §2.2, forward-looking, never as an apology
> and never as a closing "untested" list.

> These figures hold for **⟨corpus shape from §2.2 — e.g. text-layer PDFs, median ⟨n⟩
> pages⟩** ingested as a bulk drop, at **ingestion concurrency N ≤ ⟨max swept value⟩**,
> on **EKS with a Karpenter Spot NodePool pinned to `⟨instance type⟩` for ingestion
> (approximately ⟨n⟩ workers per node), Qdrant self-hosted on a dedicated On-Demand gp3
> node with INT8 scalar quantization enabled and `indexing_threshold = ⟨value⟩`, and
> bge-small-en-v1.5 at 384 dimensions served by a shared TEI service**, in **⟨region⟩**.
> Outside these conditions, re-measure.

**Two Envelope entries that are conditions, not findings.**

*Worker packing density.* The ingestion NodePool is pinned to a single instance type for
the sweep, giving roughly ⟨n⟩ workers per node. Denser packing amortises per-node warm-up
across more work and shifts the sweet spot in §3.3 to the right. The figures here are
conditional on this ratio.

*Scalar quantization.* INT8 SQ is enabled as a fixed configuration parameter, chosen for
memory footprint. **Its effect on retrieval quality is not measured in this report** and
is not claimed either way — see "Not covered".

Deliberately outside the envelope: ⟨e.g. scanned PDFs requiring OCR · GPU-backed
embedding · corpora above ⟨n⟩ GB⟩, and the entire synchronous query path.

### 2.4 Frontier X axis

> **Yields:** the parameter swept in §3 — the report's main curve is a curve *of* this.
> **From:** definition.
> **Before the run:** it must be a knob that moves end-to-end throughput. A knob on a
> component that is not the constraint produces a flat curve, and the sweep is spent for
> nothing.

**Ingestion axis:** `N` = concurrency of the ingestion pipeline — KEDA `maxReplicaCount`.

Swept **coarse to fine**: three points at N ∈ {4, 12, 24}, then two refinement points
placed by the shape those three produce. Five points total. A linear sweep of six spends
its entire budget before revealing the one failure that matters most — that the range
itself was wrong, because unit cost was still falling at the top of it.

Which ScaledJob the knob applies to — indexer only, or both stages together — is fixed
before the first point and follows from the constraint hypothesis in §3.5.

### 2.5 Measurement architecture

> **Yields:** nothing on its own. It is the precondition of §3 and §4.
> **From:** live scrape state, checked by query — not by reading config.
> **Before the run:** every "required" row returns data. A component that is not scraped
> cannot be named as the constraint, because an absent series looks exactly like an idle
> one.

| Source | Supplies | Feeds | Status |
| :--- | :--- | :--- | :--- |
| Wall clock over the frozen corpus | documents per minute, per point | §3.1 | required · available |
| `keda_scaler_metrics_value` | SQS depth; its derivative is the drain-rate cross-check | §3.1 | required · scraped |
| `kube_node_labels` by instance and capacity type | how many billable nodes existed at each moment → node-hours | §3.1, §3.4, §4.2 | required · scraped |
| `kube_node_created` + pod start time | warm-up window per node | §3.4 | required · scraped |
| cAdvisor / kube-state-metrics | worker CPU and peak RSS per component | §3.5, §5 | required · scraped |
| `run-point.py` watch loop | window boundaries, node-set changes during a run, `points_count` | §3.1 validity | required · script |
| TEI | `te_queue_size`, `te_request_inference_duration` | §3.5 Tier 2 | optional · ServiceMonitor pending |
| Qdrant `/metrics` :6333 | write / upsert latency | §3.5 Tier 2 | optional · ServiceMonitor pending |
| AWS Cost Explorer, by tag | idle spend split by component | §4.1 | required · tags activated ⟨date⟩ |

**What the two optional rows change.** Throughput tells you *that* the system stopped
scaling; per-component metrics tell you *what* stopped it. Tier 1 is provable from worker
CPU, which is scraped today. Tier 2 requires TEI and Qdrant instrumentation — if it is
absent, this report claims one tier and says so, rather than delaying the measurement or
guessing the second.

**Deliberately not instrumented in v1.0.**

*Per-execution worker summaries.* Attributing documents to individual worker executions
would require a structured exit-summary line from each worker plus log-derived metrics. It
is not needed here: the corpus is frozen, so document counts come from the fixture, and
drain rate comes from queue depth. Node loss during a run — the one thing that could
distort a point — is detected by `run-point.py` as a change in the node set while the
queue is non-empty.

*Go API request metrics.* No query-path run exists to consume them, and instrumentation
without a consumer generates work rather than evidence. Deferred to v2.0 together with the
run that needs it.

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
> **From:** the `sweep` run — five points over the frozen corpus.
> **Before the run:** identical image digests at every point; only the concurrency value
> changes. Between points, both SQS queues at depth zero, the ingestion NodePool at zero
> nodes, and the Qdrant collection wiped — all three enforced by `run-point.py` preflight.

| N | Config commit | Docs/min | Wall time | Node-hours spot / on-demand | $/run | $/1M docs | Saturation signal | Interruptions |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | | | |
| 12 | | | | | | | | |
| 24 | | | | | | | | |
| ⟨refine⟩ | | | | | | | | |
| ⟨refine⟩ | | | | | | | | |

**Config commit** — the sweep parameter lives in Git, so each point has its own commit.
That is expected and does not break the comparison; the application image digests in the
header are what must stay identical, and they are frozen against a recorded baseline.

**Docs/min is measured twice, from independent sources.** Wall clock against the known
corpus size gives the point value; the derivative of SQS queue depth gives the shape over
time and catches a run that stalled and recovered rather than draining steadily. If the
two disagree by more than a few percent, the point is not trusted.

**$/run is computed, not billed.** AWS billing updates roughly daily and cannot see a
twenty-minute run at all. Because the NodePool is pinned to one instance type, this is a
product rather than a sum over types:

```
$/run = node_hours_spot × price_spot + node_hours_on_demand × price_on_demand
```

Node count over time comes from `kube_node_labels`, integrated across the run window.

**Saturation signal** — which component was at its ceiling when throughput stopped growing
at this point. One of: chunker CPU pinned · TEI request queue growing · Qdrant write
latency rising · queue not draining despite idle workers. This column is the raw material
of §3.5; an empty cell means that point contributes nothing to the constraint ladder.

**Interruptions** — node loss detected during the run. **Validity rule:** a point with
interruptions carries extra warm-up cost that belongs to no concurrency level, and its
`$/1M docs` cell is not comparable. Either re-run the point or mark the figure ᴱ and
exclude it from the curve fit. Do not average it in silently.

### 3.2 Chart — throughput and unit cost against concurrency

> **Yields:** the visual that carries §3.3.
> **From:** two columns of §3.1, nothing else.

One chart, dual Y axis, X axis = N:

- **Left axis:** docs/min. Expected shape — rises, then flattens.
- **Right axis:** $/1M docs. Expected shape — falls, reaches a minimum, rises again.

Plot script and generated image committed under `docs/report/charts/`.

### 3.3 Knee, sweet spot, and waste boundary

> **Yields:** the `maxReplicaCount` guardrail in §5.
> **From:** reading three points off §3.1 and §3.2.

| Point | How it is identified | N | Evidence from §3.1 |
| :--- | :--- | :--- | :--- |
| **Knee** | the last N where docs/min still rose meaningfully over the previous point — state the threshold used, e.g. under 10 % gain counts as flat | | |
| **Sweet spot** | the N with the lowest value in the `$/1M docs` column | | |
| **Waste boundary** | the first N where a step up raises `$/run` substantially while adding under 10 % throughput | | |

**Boundary rule.** A minimum that lands on the lowest or highest N actually swept sits on
the edge of the range and is not proven — there is no descending branch on one side of it.
The refinement pass (§2.4) exists to place points on both sides of the candidate minimum;
if it still lands on an edge after refinement, say so rather than claiming a minimum.

**The gap between knee and sweet spot is the finding of this section.** State it as a
sentence: how much extra you pay per document to run at the knee instead of the sweet
spot, and how much throughput you give up going the other way. The guardrail is set at the
sweet spot; the knee is documented as the ceiling for a hurry.

### 3.4 Why unit cost rises again at high concurrency

> **Yields:** the mechanism behind the U-curve. Without it §3.3 is a chart with no
> explanation and the reader assumes noise.
> **From:** node creation and first-pod-ready timestamps, per node, per run.

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

| N | Warm-up (created → first pod ready) | Productive work | Consolidation tail | Overhead share |
| :--- | :--- | :--- | :--- | :--- |
| ⟨low⟩ | | | | |
| ⟨high⟩ | | | | |

The report needs the overhead *share*, not its attribution across provisioning, image pull
and runtime init — which is why the sub-phase breakdown is not instrumented. For
scale-to-zero ephemeral workers this is the dominant cost effect and is almost never
quantified in published architectures.

### 3.5 Constraint ladder

> **Yields:** the constraint named in BLUF and the price of removing it.
> **From:** the saturation column of §3.1 plus per-component metrics, read at each point.
> **Note:** Tier 1 is provable from worker CPU alone. Tier 2 requires TEI and Qdrant
> metrics; if they were unavailable, this section reports one tier.

| Tier | Component | Proof metric and where it saturated | Relieved by | Cost to remove ᴬ |
| :--- | :--- | :--- | :--- | :--- |
| 1 | | | | |
| 2 | | | | |

**What proves a second tier.** A constraint ladder is the order in which ceilings are hit.
A tier counts as proven only when the previous one was actually relieved and a new
saturation was then observed — never because its numbers "looked close".

Sweeping concurrency relieves tiers on its own. If chunker CPU is the ceiling at N=4, then
at N=24 there are six times as many chunkers and that ceiling is gone; whatever saturates
instead — TEI queue depth, Qdrant write latency — is a genuinely proven Tier 2, observed
under relief rather than guessed. This is the reason the sweep runs to 24 rather than 12.

**No third tier is claimed**, regardless of what the numbers suggest. An unproven tier
weakens the tiers that were proven.

**Hypothesis recorded before the run.** The original design assumed the ceiling would be
TEI inference. On a book-length PDF corpus the likelier first ceiling is the Stage-1
chunker: PyMuPDF text extraction on a 300-page PDF is single-threaded CPU work and may
dominate embedding time by an order of magnitude. If the hypothesis inverts, the inversion
stays in the report — *"we expected to saturate inference and saturated PDF parsing
instead"* is what makes the measurement credible.

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
> **From:** the `idle` run — a 24-hour window with zero traffic, spend pulled by tag at
> daily granularity. Lines Cost Explorer cannot resolve are computed from the price list
> and marked ᴬ.
> **Before the run:** cost allocation tags applied **and activated** in the billing
> console — activation is a separate step, applies going forward only, up to 24 hours of
> delay. During the window: no deploys, no config changes, no manual commands. ArgoCD
> reconciliation stays on; it is part of the floor.

For an asynchronous ingestion architecture the floor is where the entire value proposition
lives, so it is split rather than totalled.

**Block A — shared platform.** Exists whether or not this feature is deployed. Shown in
full for honesty. Not divided by an assumed number of tenant features — that divisor would
be arbitrary, and Blocks B and C already answer both questions a reader can ask.

| Line | Fixed / Variable | $/month | |
| :--- | :--- | :--- | :--- |
| EKS control plane | Fixed | | plan assumes ~$73 — verify |
| `core-on-demand` node group — CoreDNS, ArgoCD, Cilium, Prometheus, Grafana | Fixed | | |
| NAT Gateway — hourly charge plus per-GB processing | Fixed | | |
| EBS gp3 — Prometheus 10 Gi + Loki 10 Gi | Fixed | | |
| **Block A total** | | | |

**Block B — feature-dedicated.** Disappears entirely if the RAG feature is removed.
**This is the number that goes to BLUF and drives §4.3.**

| Line | Fixed / Variable | $/month | |
| :--- | :--- | :--- | :--- |
| `database-on-demand` node group — Qdrant | Fixed | | see quantization note below |
| EBS gp3 — Qdrant volume | Fixed | | |
| TEI serving capacity at idle | ⟨fixed or scale-to-zero — confirm⟩ | | |
| VPC Interface Endpoints — Bedrock, SQS, S3, billed per AZ | Fixed | | |
| S3 storage — raw plus Glacier IR after 7 days | Variable with corpus size | | |
| SQS requests | Variable | | ~0 at idle |
| KEDA ScaledJob ingestion compute | Variable, floor = 0 | 0.00 | |
| **Block B total** | | | |

**Block C — standalone scenario.** `A + B`, one line: what this feature would cost as the
only workload on its own cluster. The number a greenfield reader needs, and the honest
counterweight to the shared-platform framing.

**Three notes this table exists for.**

*The NAT Gateway* is the hidden line of this architecture class and is missing from almost
every published version of it. Billed hourly regardless of traffic, and again per gigabyte
processed — including container image pulls and the indexer's model weight downloads from
HuggingFace.

*Quantization sets the database instance class.* INT8 scalar quantization is enabled as a
fixed configuration parameter. At 1M points × 384 dimensions, float32 vectors require
1.536 GB and INT8 requires 0.384 GB ᴬ — which is why the `database-on-demand` line above
is as small as it is. Measured Qdrant RSS at teardown: ⟨R5⟩. **The retrieval cost of this
compression is not measured here** — see "Not covered".

*Article 1 advertised "$0.00 on idle."* This table states for exactly how many rows that
is true. A deepening of the claim with data in hand, not a retraction — which is the more
credible of the two positions.

### 4.2 Marginal — cost per unit at the sweet spot

> **Yields:** the coefficient in the spine equation.
> **From:** the sweep point at the sweet-spot N, decomposed by cost component.
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
> **From:** arithmetic on measured sweep data against published Fargate pricing. No
> additional run.

The relevant alternative is not a different platform — the cluster exists regardless. It is
the compute mode for the same ingestion Jobs. Fargate removes node provisioning, per-node
image pull and Spot interruption handling entirely, and charges per vCPU-second and
GB-second at a premium over EC2 Spot.

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
| Budget alarm | `$⟨§4.1 Block B × 1.4⟩` | §4.1 | `terraform/budgets.tf` |

---

## Not covered in v1.0 — declared

*Stated rather than omitted silently, and phrased as scope, not apology.*

| Not included | What it would have supported | Why |
| :--- | :--- | :--- |
| Query path under load — latency percentiles, error rate, ingest/query contention on Qdrant | Whether the p95 target holds under real traffic, and the cost of serving queries | Requires its own frontier axis (API and TEI replica count × RPS) and its own denominator. A single fixed-replica measurement is a number without an axis and supports no decision. The `p95 < 200 ms` figure in `architecture.md` is a design target and is labelled as unverified. Scoped to v2.0 |
| Retrieval configuration study — quantization variants, rescore and oversampling, dense vs sparse vs hybrid ablation, `hnsw_ef` sweep | Which retrieval configuration to run in production, and what each costs in recall and latency | Its own frontier axis, incompatible with the ingestion-concurrency axis of this report. INT8 scalar quantization is treated here as a fixed parameter chosen for memory footprint, with no claim about its retrieval cost. The study runs locally against the collection snapshot committed at teardown (R5) — no cluster required. Scoped to v2.0 |
| Spot interruption injected under load | Reliability economics — cost of the resilience mechanism, recovery time, duplicate count | Idempotency via deterministic point IDs is designed in and verifiable by count comparison; pricing the mechanism needs its own run and its own instrumentation. Scoped to v2.0 |
| Per-execution worker attribution | Documents and exit reason per worker execution | Not required for throughput, which comes from the frozen corpus and queue depth; needed only for the reliability run above |
| Third constraint tier | §3.5 | At most two tiers are provable from this sweep; a third would be a guess and would weaken the ones that were proven |
| Regression against a previous report | — | Unavailable at v1.0; becomes the strongest available section from v2.0 |
