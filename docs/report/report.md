# Executive Engineering Report — simple-rag

What asynchronous document ingestion actually costs, and where adding concurrency stops
buying throughput.

| | |
| :--- | :--- |
| Report | `simple-rag` · v1.0 · ⟨date⟩ |
| System under test | chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` · ⟨date⟩ |
| Envelope | text-layer PDF corpus, bulk drop · N ≤ ⟨max swept⟩ · EKS + Karpenter Spot, self-hosted Qdrant, TEI `bge-small-en-v1.5` · ⟨region⟩ |
| Executions | `00-baseline` · `01-ingestion` |
| Raw data | `executions/00-baseline/data/` · `executions/01-ingestion/data/` |
| Supersedes | — |
| Changes | — (first revision) |

> All figures are measured unless marked: ᴬ arithmetic · ᴹᵒ modeled · ᴱ estimated.

**Scope.** This report prices one path of one feature: asynchronous document ingestion. The
synchronous query path is deliberately out of scope — it has its own frontier axis and its
own denominator, and mixing the two produces a number that supports no decision. The
Kubernetes platform both paths run on exists for other workloads too; §4.1 separates what
belongs to the feature from what is shared, and prices both.

---

## Coverage

What this revision measured, what it declares without measuring, and what is out of scope. A
reader who cannot see the boundary of a report cannot trust any number inside it.

| Area | Status | Evidence | Since |
| :--- | :--- | :--- | :--- |
| Ingestion throughput vs concurrency | Measured | §3.1 · `01-ingestion` | v1.0 |
| Ingestion unit cost `$/1M docs` | Derived ᴬ | §3.1 · `01-ingestion` C4, C5 | v1.0 |
| Knee, sweet spot, waste boundary | Measured | §3.3 | v1.0 |
| Warm-up share of node-hours | Measured | §3.4 · `01-ingestion` C6 | v1.0 |
| Constraint ladder — Tier 1 | Measured | §3.5 · E10 | v1.0 |
| Constraint ladder — Tier 2 | ⟨Measured / **Declared, not measured**⟩ | §3.5 · conditional on E20/E30 landing | v1.0 |
| Idle floor, split A / B / C | Measured | §4.1 · `00-baseline` §5 | v1.0 |
| Marginal unit economics | Derived ᴬ | §4.2 · `01-ingestion` C7 | v1.0 |
| Amortization across volumes | Derived ᴬ | §4.3 · C8 | v1.0 |
| Break-even vs Fargate | Derived ᴬ | §4.4 · C9 | v1.0 |
| Query path — latency, cost per query, contention | **Declared, not measured** | `02-inference`, planned | v1.1 |
| Retrieval quality vs quantization | **Declared, not measured** | `03-retrieval`, runs locally from the teardown snapshot | v1.1 |
| Reliability economics — Spot interruption under load | Out of scope | — | — |
| Per-execution worker attribution | Out of scope | — | — |
| Third constraint tier | Out of scope | — | — |
| Regression vs previous revision | Out of scope | no predecessor at v1.0 | v1.1 |

**Measured** — evidence exists and this report cites it · **Derived** — arithmetic on a
measured figure · **Declared, not measured** — named so its absence is visible, scheduled for
a stated revision · **Out of scope** — deliberately not this report's question.

> Sections 6–8 of the report template (reliability economics, levers, quality/cost
> trade-off) have no material in v1.0 and are therefore absent, not blank. Their absence is
> a row in this table. **A report with the sections that have material is complete with
> declared coverage — not a draft.**

---

## 1. BLUF

*Conclusion first, evidence after. Written **last**, from finished numbers — an executive
reads the first thirty seconds and stops.*

An absolute number decides nothing. Every row carries a reference value and a plain sentence
saying what it means.

| Metric | Result | Reference | What it means |
| :--- | :--- | :--- | :--- |
| Ingestion cost at the optimum | ⟨$X / 1M docs⟩ | vs ⟨$A on Fargate, §4.4⟩ | what a million documents cost to ingest, and whether Spot beat the serverless mode |
| Feature idle floor | ⟨$Y / month⟩ | vs ⟨$Z standalone, Block C⟩ | what this feature burns on a weekend with zero traffic, on a platform that already exists |
| Peak stable ingest rate | ⟨Z docs/min at N=n⟩ | plateau begins at N=⟨m⟩ | past this concurrency you pay more and get nothing |
| Primary constraint | ⟨component⟩ | cost to remove ⟨$C⟩ ᴬ | which component decides throughput, and the price of the next scaling step |

**Verdict:** ship / ship with guardrails / do not ship — one sentence, one action.

---

## 2. Workload Contract & Envelope

The unit of work, the frozen corpus, the configuration under which every figure holds, and
the measurement architecture are **givens shared by every execution** and live in
`executions/00-baseline/index.md` §2–§6 and `metrics.md`.

Carried here because a reader cannot follow §3 without them:

| | |
| :--- | :--- |
| **Unit of work** | ⟨one PDF ingested end to end, counted when its final chunk batch is acknowledged by Qdrant⟩ — one denominator, never two (`00-baseline` §3) |
| **Corpus** | `zabiullah/pdf-books-collection`, frozen · ⟨n⟩ documents · median ⟨n⟩ pages, p95 ⟨n⟩ (`00-baseline` §3) |
| **Window** | opens at the first `s3:ObjectCreated`, closes at ingestion NodePool zero + 5 min. Upload is outside the system under test (`01-ingestion` §1) |
| **Envelope** | `00-baseline` §6 |
| **Blind spots** | TEI and Qdrant instrumentation was ⟨available / pending⟩; a component that is not observed cannot be named as a constraint (`00-baseline` §7.2) |

**Two envelope entries that are conditions, not findings.**

*Worker packing density.* The ingestion NodePool is pinned to a single instance type, giving
≈ ⟨n⟩ workers per node. Denser packing amortises per-node warm-up across more work and
shifts the sweet spot in §3.3 to the right. Every figure here is conditional on this ratio.

*Scalar quantization.* INT8 SQ is enabled as a fixed configuration parameter, chosen for
memory footprint. **Its effect on retrieval quality is not measured in this report** and is
not claimed either way.

---

## 3. Efficiency Frontier

*This section answers one engineering question: **how do we configure it?** The axis is
concurrency, the horizon is a single run, and the person turning the knob is the engineer.*

*Its output is one number §4 consumes — marginal cost per unit at the best setting — plus the
concurrency ceiling that becomes a guardrail in §5.*

*The finding it exists to produce: throughput plateaus at one concurrency level, and unit
cost bottoms out at a **different**, usually lower one. Most engineers tune to the first and
never discover the second.*

Source: `executions/01-ingestion/` — five points, swept coarse to fine over N ∈ {4…24}.

### 3.1 Run matrix

| N | Docs/min | Wall time | Node-hours (Spot / On-Dem) | $/run ᴬ | $/1M docs ᴬ | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | |
| 12 | | | | | | |
| 24 | | | | | | |
| ⟨refine⟩ | | | | | | |
| ⟨refine⟩ | | | | | | |

Config commits, interruption counts and per-point validity decisions stay in
`01-ingestion` §2–§3; they are audit trail, not report material. Excluded points and the
rule applied: ⟨⟩.

**Docs/min is measured twice, from independent sources.** Wall clock against the known corpus
size gives the point value; the derivative of SQS queue depth gives the shape over time and
catches a run that stalled and recovered rather than draining steadily.

**$/run is computed, not billed.** AWS billing updates roughly daily and cannot see a
twenty-minute run at all. Because the NodePool is pinned to one instance type, this is a
product rather than a sum over types:

```
$/run = node_hours_spot × price_spot + node_hours_on_demand × price_on_demand
```

**Saturation signal** — which component was at its ceiling when throughput stopped growing.
Hand-recorded per point; an empty cell means that point contributes nothing to §3.5.

### 3.2 Chart — throughput and unit cost against concurrency

One chart, dual Y axis, X = N. Left: docs/min — rises, then flattens. Right: `$/1M docs` —
falls, reaches a minimum, rises again.

Plot script and image: `executions/01-ingestion/scripts/plot-frontier.py` → `charts/`.

### 3.3 Knee · Sweet spot · Waste boundary

| Point | How it is identified | N | Evidence |
| :--- | :--- | :--- | :--- |
| **Knee** | last N where docs/min still rose meaningfully — threshold used: ⟨⟩ | | §3.1 |
| **Sweet spot** | lowest `$/1M docs` | | §3.1 |
| **Waste boundary** | first N where `$/run` rises substantially for under 10 % throughput | | §3.1 |

**Boundary rule.** A minimum landing on the lowest or highest N actually swept sits on the
edge of the range and is **not proven** — there is no descending branch on one side of it.
The refinement pass exists to place points on both sides of the candidate minimum; if it
still lands on an edge, say so rather than claiming a minimum.

**The gap between knee and sweet spot is the finding of this section.** State it as one
sentence: how much extra you pay per document to run at the knee instead of the sweet spot,
and how much throughput you give up going the other way. The guardrail is set at the sweet
spot; the knee is documented as the ceiling for a hurry.

### 3.4 Why unit cost rises again at high concurrency

Without the mechanism the chart reads as noise.

Every node is billed from the moment it is provisioned, but produces work only after it has
booted, pulled the container image and initialised the runtime — roughly ⟨60–90⟩ s in this
system. It is billed again for a short tail after the last document, until consolidation
removes it. Both windows produce zero units at full price.

At low N that overhead is spread across a long run and barely registers. At high N the
corpus drains fast, but many nodes each pay the same fixed warm-up and each do only a few
minutes of real work. The overhead share of every billed node-hour grows and cost per
document turns back up — even though wall-clock time keeps improving. That is the entire
mechanism of the U-curve.

| N | Warm-up (created → first pod ready) | Productive work | Consolidation tail | Overhead share |
| :--- | :--- | :--- | :--- | :--- |
| ⟨low⟩ | | | | |
| ⟨high⟩ | | | | |

The report needs the overhead *share*, not its attribution across provisioning, image pull
and runtime init — which is why the sub-phase breakdown is not instrumented. For
scale-to-zero ephemeral workers this is the dominant cost effect and is almost never
quantified in published architectures.

### 3.5 Constraint ladder

| Tier | Component | Proof metric and where it saturated | Relieved by | Cost to remove ᴬ |
| :--- | :--- | :--- | :--- | :--- |
| 1 | | | | |
| 2 | | | | |

**What proves a second tier.** A ladder is the order in which ceilings are hit. A tier counts
as proven only when the previous one was **actually relieved** and a new saturation was then
observed — never because its numbers looked close.

Sweeping concurrency relieves tiers on its own: if chunker CPU is the ceiling at N=4, then at
N=24 there are six times as many chunkers and that ceiling is gone; whatever saturates
instead is a genuinely proven Tier 2. This is the reason the sweep runs to 24 rather than 12.

**No third tier is claimed**, regardless of what the numbers suggest. An unproven tier
weakens the tiers that were proven, and a reader who catches one speculative claim discounts
the rest.

**Hypothesis, recorded before the first point** (`01-ingestion` §1): the ceiling was expected
to be the Stage-1 chunker, not TEI — PyMuPDF extraction on a 300-page PDF is single-threaded
CPU work and may dominate embedding time by an order of magnitude, while the original design
assumed inference would saturate first. Outcome: ⟨confirmed / inverted — and if inverted, the
inversion stays here verbatim⟩.

---

## 4. Cost Structure

*This section answers a different question from §3: **should it be built this way at all?**
The axis is monthly volume, the horizon is a year of ownership, and the person turning the
knob is the business, not the engineer.*

```
Monthly Cost = Floor + ( Marginal_per_unit × Volume )
                 ↑                 ↑
               §4.1        §3 supplies this coefficient, via §4.2
```

### 4.1 Floor — what it costs at zero load

Measured over a 24 h idle window with cost attribution active, split rather than totalled.
Full line-by-line audit: `executions/00-baseline/index.md` §5.

| Block | What it is | $/month |
| :--- | :--- | :--- |
| A | shared platform — exists without this feature | |
| **B** | **feature-dedicated — disappears with it. The BLUF number** | |
| C | standalone greenfield — A + B | |

Not divided by an assumed number of tenant features: that divisor would be arbitrary, and
Blocks B and C already answer both questions a reader can ask.

**Three notes this table exists for.**

*The NAT Gateway* is the hidden line of this architecture class and is missing from almost
every published version of it. Billed hourly regardless of traffic, and again per gigabyte
processed — including container image pulls and the indexer's model weight downloads from
HuggingFace.

*Quantization sets the database instance class.* At 1M points × 384 dimensions, float32
vectors require 1.536 GB and INT8 requires 0.384 GB ᴬ — which is why the dedicated database
line is as small as it is. Measured Qdrant RSS at teardown: ⟨⟩. **The retrieval cost of this
compression is not measured here.**

*Article 1 advertised "$0.00 on idle."* This table states for exactly how many rows that is
true: ⟨n⟩ of ⟨m⟩. A deepening of the claim with data in hand, not a retraction — which is the
more credible of the two positions.

### 4.2 Marginal — cost per unit at the sweet spot

Floor lines excluded by definition; mixing them inflates the coefficient and corrupts §4.4.
Components sum to the total.

| Component | $/1M docs | Share |
| :--- | :--- | :--- |
| Stage-1 chunker compute | | |
| Stage-2 indexer compute | | |
| TEI serving compute attributable to ingestion | | |
| Warm-up and consolidation overhead (§3.4) | | |
| SQS requests ᴬ | | |
| S3 requests ᴬ | | |
| NAT data processing | | |
| **Total marginal** | | 100 % |

### 4.3 Amortization — where the floor stops dominating

Arithmetic on Block B and §4.2. No run. `Effective $/doc = ( Block B + Marginal × V ) ÷ V`

| Monthly volume | Effective $/doc ᴬ | Floor share of total |
| :--- | :--- | :--- |
| 1 000 | | |
| 10 000 | | |
| 100 000 | | |
| 1 000 000 | | |

Block B is the right floor here: for a feature on a cluster that exists anyway, the question
is what *this feature* costs to keep alive, not what the platform costs. Below the volume
where floor share drops under half — ⟨V⟩ — you are paying mostly for the feature to exist
rather than for work done. That volume is the lower bound of where this design makes
economic sense.

### 4.4 Break-even — Karpenter Spot versus Fargate for the same Jobs

The relevant alternative is not a different platform — the cluster exists regardless. It is
the compute mode for the same ingestion Jobs. Fargate removes node provisioning, per-node
image pull and Spot interruption handling entirely, and charges per vCPU-second and
GB-second at a premium over EC2 Spot.

The comparison is direct because §3.1 already measured what a run consumes:

| | Karpenter Spot (measured) | Fargate (arithmetic ᴬ) |
| :--- | :--- | :--- |
| vCPU-hours per 1M docs | | same workload, same figure |
| GB-hours per 1M docs | | same workload, same figure |
| Warm-up overhead paid (§3.4) | | per-task cold start, no per-node image pull |
| Effective $/1M docs | | ᴬ |
| Interruption handling required | yes — SIGTERM path in the workers | no |
| Feature floor impact | 0 at idle | 0 at idle |

Output is one sentence of the shape: *"Spot is cheaper per million documents by X %, and that
discount is paid for with the interruption-handling code in the workers; below Y documents
per month the difference is smaller than the engineering cost of maintaining it."*

---

## 5. Guardrails

A recommendation is prose and gets forgotten. A guardrail is a config value, sourced from a
number in this report, that can be committed to a file. **If it cannot be committed, it does
not belong in this table.** Rows whose source number does not survive the runs are deleted,
not left blank.

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Ingestion concurrency ceiling | `maxReplicaCount: ⟨§3.3 sweet spot⟩` | §3.3 | `deploy/k8s/.../scaledjob.yaml` |
| Indexer memory limit | `limits.memory: ⟨peak RSS + 30 %⟩` | E11 | `deploy/k8s/apps/indexer/` — currently 2Gi |
| Chunker memory limit | `limits.memory: ⟨peak RSS + 30 %⟩` | E11 | `deploy/k8s/apps/chunker/` |
| Max input file size | `MAX_ALLOWED_SIZE_BYTES: ⟨confirm 100 MB⟩` | §3.5 tail behaviour · ADR-0001 | `apps/chunker/` env |
| Chunks per SQS message | `⟨confirm 30⟩` | §4.2 SQS line · ADR-0004 | `apps/chunker/` env |
| Ingestion backlog alert | `⟨§3.1 drain rate × alert window⟩` | §3.1 | `prometheus/rules.yaml` |
| Budget alarm | `$⟨Block B × 1.4⟩` | §4.1 | `terraform/budgets.tf` |

---

## Out of scope for this revision

Stated rather than omitted silently, and phrased as scope, not apology.

| Not included | What it would have supported | Why |
| :--- | :--- | :--- |
| Query path under load — latency percentiles, error rate, ingest/query contention on Qdrant | Whether the p95 target holds under real traffic, and the cost of serving queries | Its own frontier axis (API and TEI replicas × RPS) and its own denominator. A single fixed-replica measurement is a number without an axis. The `p95 < 200 ms` figure in `architecture.md` is a design target and is labelled unverified. Planned as `02-inference`, v1.1 |
| Retrieval configuration study — quantization variants, rescore and oversampling, dense vs sparse vs hybrid, `hnsw_ef` sweep | Which retrieval configuration to run in production, and what each costs in recall and latency | Its own axis, incompatible with the ingestion-concurrency axis here. INT8 SQ is treated as a fixed parameter chosen for memory footprint, with no claim about retrieval cost. Runs locally against the collection snapshot captured at teardown (`00-baseline` §8) — no cluster required. Planned as `03-retrieval`, v1.1 |
| Spot interruption injected under load | Reliability economics — cost of the resilience mechanism, recovery time, duplicate count | Idempotency via deterministic point IDs is designed in and verifiable by count comparison; pricing the mechanism needs its own run and instrumentation |
| Per-execution worker attribution | Documents and exit reason per worker execution | Not required for throughput, which comes from the frozen corpus and queue depth; needed only for the reliability run above |
| Third constraint tier | A deeper §3.5 | At most two tiers are provable from this sweep; a third would be a guess and would weaken the ones that were proven |
| Lambda as the build alternative | A more dramatic §4.4 | The cluster exists regardless — the honest alternative is a different compute mode on the same platform, which is Fargate |
| Regression against a previous report | — | Unavailable at v1.0; becomes the strongest available section from v1.1 |

> An execution that ran and turned out insignificant belongs here too, with its finding.
> "Measured, contributed under ⟨n⟩ % of cost, omitted" is a result, and it stops the question
> being asked again next revision.

---

## Publication gate — delete this block before publishing

- [ ] Every number traceable to a file under an execution's `data/`
- [ ] Every non-measured number marked ᴬ / ᴹᵒ / ᴱ
- [ ] No ⟨⟩ placeholder survives
- [ ] BLUF written **last**, every row with a reference value and a plain-language meaning;
  the verdict names one action
- [ ] Every guardrail is a config value with a source and a file — no blank rows
- [ ] Every section yields at least one number reaching BLUF or Guardrails
- [ ] No third tier · no priced SLA breach · no closing "future work" list
- [ ] Invalid points excluded from the curve fit, and the exclusion stated
- [ ] The unqualified "$0.00 idle" claim from article 1 is retired by §4.1 — as a deepening
  with data in hand, not as a correction
- [ ] `architecture.md` p95 line relabelled as an unverified design target
- [ ] Teardown snapshot uploaded and referenced from the out-of-scope table
