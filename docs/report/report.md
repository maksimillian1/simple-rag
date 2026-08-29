# Executive Engineering Report — simple-rag

What asynchronous document ingestion costs on an event-driven Kubernetes platform, where
adding concurrency stops buying throughput, and at what monthly volume the design pays for
itself. This report prices one path of one feature: ingestion. The synchronous query path has
its own axis and its own denominator, and mixing the two produces a number that supports no
decision.

- **Report** — `simple-rag` · v1.0 · ⟨date⟩
- **System under test** — chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` · commit `⟨sha⟩` · ⟨date⟩
- **Envelope** — text-layer PDF corpus, bulk drop · N ≤ ⟨max swept⟩ · EKS + Karpenter Spot, self-hosted Qdrant, TEI `bge-small-en-v1.5` · ⟨region⟩
- **Executions** — `00-baseline` · `01-ingestion`
- **Raw data** — `executions/00-baseline/data/` · `executions/01-ingestion/data/` · charts in `assets/`
- **Figures** — measured unless marked: ᴰ derived · ᴿ recorded · ᴱ estimated
- **Supersedes** — —
- **Changes** — first revision

---

## Coverage

| Area | Status | Evidence | Cost of absence | Since |
| :--- | :--- | :--- | :--- | :--- |
| Ingestion throughput vs concurrency | measured | §3.1 · `01-ingestion` §3 | — | v1.0 |
| Ingestion unit cost per 1M documents | derived ᴰ | §3.1 · `01-ingestion/D18` | — | v1.0 |
| Knee, sweet spot, waste boundary | measured | §3.3 | — | v1.0 |
| Warm-up share of node-hours | measured | §3.4 · `01-ingestion/D19` | — | v1.0 |
| Constraint ladder — Tier 1 | measured | §3.5 · `01-ingestion/M5` | — | v1.0 |
| Constraint ladder — Tier 2 | ⟨measured · declared, not measured⟩ | §3.5, conditional on `01-ingestion` M8–M10 landing | which component becomes the ceiling once the chunker is relieved, and what the next scaling step costs | v1.0 |
| Idle floor, split A / B / C | measured | §4.1 · `00-baseline` §2 Floor | — | v1.0 |
| Marginal unit economics | derived ᴰ | §4.2 · `01-ingestion/D20` | — | v1.0 |
| Amortization across volumes | derived ᴰ | §4.3 · `01-ingestion/D21` | — | v1.0 |
| Break-even against Fargate | derived ᴰ | §4.4 · `01-ingestion/D22` | — | v1.0 |
| Query path — latency, cost per query, ingest/query contention on Qdrant | declared, not measured | — | whether the `p95 < 200 ms` design target holds under real traffic, and what serving a query costs. It carries its own axis (API and TEI replicas × arrival rate) and its own denominator | v1.1 |
| Retrieval quality against quantization | declared, not measured | — | what INT8 compression costs in recall, and which retrieval configuration to run in production. INT8 SQ is a frozen given here, chosen for memory footprint, with no claim about retrieval | v1.1 |
| Reliability economics — Spot interruption injected under load | out of scope | — | the price of the resilience mechanism: work lost, duplicates, recovery time. Idempotency via deterministic point IDs is designed in and verifiable by count comparison; pricing it needs its own run | — |
| Per-execution worker attribution | out of scope | — | documents and exit reason per worker execution. Throughput comes from the frozen corpus and queue depth; this is needed only for the reliability run above | — |
| Third constraint tier | out of scope | — | a deeper §3.5. At most two tiers are provable from this sweep; a third would be a guess and would weaken the two that were proven | — |
| Lambda as the build alternative | out of scope | — | a more dramatic §4.4. The cluster exists regardless, so the honest alternative is a different compute mode on the same platform — which is Fargate | — |
| Reliability, levers and quality/cost sections | out of scope | — | template §6–§8 have no material at v1.0 and are absent rather than blank | — |
| Regression against a previous revision | out of scope | no predecessor | — | v1.1 |

---

## 1. BLUF

* **Unit cost at optimum** — ⟨$X / 1M docs⟩ (vs ⟨$A on Fargate, §4.4⟩) — what a million documents cost to ingest, and whether Spot beat the serverless mode
* **Idle floor, Block B** — ⟨$Y / month⟩ (vs ⟨$Z standalone, Block C⟩) — what the feature burns on a weekend with zero traffic, on a platform that exists anyway
* **Peak stable rate** — ⟨Z docs/min at N=n⟩ (knee at ⟨N=m⟩) — past this concurrency you pay more and get nothing
* **Primary constraint** — ⟨component⟩ ᴿ (headroom cost ⟨$C⟩ ᴰ) — which component decides throughput, and the price of the next scaling step

**Verdict** — ⟨ship · ship with guardrails · do not ship⟩. ⟨One sentence, one action.⟩

---

## 2. Workload Contract & Envelope

- **Unit of work** — one source document, complete when its last chunk is upserted and counted in Qdrant `points_count`. One denominator, never two
- **Workload fixture** — `⟨corpus⟩`, bulk drop · median ⟨n⟩ pages, p95 ⟨n⟩ · frozen ⟨date⟩ `⟨sha⟩` (`00-baseline` §2 Input fixture)
- **Denominator** — ⟨N⟩ documents, from `00-baseline` §2
- **Envelope** — `00-baseline` §2 Envelope. The window opens at the first `s3:ObjectCreated` and closes at ingestion NodePool zero plus five minutes; upload itself is outside the system under test
- **Metric sources** — `00-baseline/metrics.md` · `01-ingestion/metrics.md`. TEI and Qdrant instrumentation was ⟨available · pending⟩ during the campaign, and a component that is not observed is not named as a constraint

Two envelope entries are conditions rather than findings.

*Worker packing density.* The ingestion NodePool is pinned to a single instance type, giving
≈ ⟨n⟩ workers per node. Denser packing amortises per-node warm-up across more work and shifts
the sweet spot in §3.3 to the right. Every figure below is conditional on this ratio.

*Scalar quantization.* INT8 SQ is enabled as a fixed configuration parameter, chosen for
memory footprint. Its effect on retrieval quality is not measured here and is not claimed
either way.

---

## 3. Efficiency Frontier

Throughput plateaus at one concurrency level and unit cost bottoms out at a different, lower
one. Source: `executions/01-ingestion/` — five points swept coarse to fine over N ∈ {4…24}.

### 3.1 Run matrix

| N | Docs/min | Wall time | Node-hours (Spot / On-Dem) | $/run ᴰ | $/1M docs ᴰ | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | ᴿ |
| 12 | | | | | | ᴿ |
| 24 | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | ᴿ |

Excluded points and the rule applied: ⟨⟩. Config commits, interruption counts and per-point
validity decisions are audit trail and stay in `01-ingestion` §2.

Docs/min is measured twice from independent sources: wall clock against the known corpus size
gives the point value, and the derivative of SQS queue depth gives the shape over time, which
catches a run that stalled and recovered rather than draining steadily.

`$/run` is computed, not billed — AWS billing updates roughly daily and cannot see a
twenty-minute run at all. Because the NodePool is pinned to one instance type it is a product
rather than a sum over types:

```
$/run = node_hours_spot × price_spot + node_hours_on_demand × price_on_demand
```

### 3.2 Chart — throughput plateau vs unit-cost curve

`assets/frontier.svg` — from `executions/01-ingestion/data/frontier.csv`. One chart, dual Y
axis, X = N. Left: docs/min, rising then flat. Right: `$/1M docs`, falling to a minimum and
rising again.

### 3.3 Knee · sweet spot · waste boundary

| Point | How it is identified | N | Evidence |
| :--- | :--- | :--- | :--- |
| Knee | last N where docs/min still rose meaningfully — threshold used ⟨⟩ | | §3.1 |
| Sweet spot | lowest `$/1M docs` | | §3.1 |
| Waste boundary | first N where `$/run` rises substantially for under 10 % throughput | | §3.1 |

⟨One sentence: how much extra per document you pay to run at the knee instead of the sweet
spot, and how much throughput you give up going the other way.⟩ The guardrail in §5 is set at
the sweet spot; the knee is documented as the ceiling for a hurry.

A minimum landing on the lowest or highest N actually swept sits on the edge of the range and
is not proven — there is no descending branch on one side of it. ⟨State whether the refinement
pass placed points on both sides of the minimum.⟩

### 3.4 Shape of the cost curve

Every node is billed from the moment it is provisioned but produces work only after it has
booted, pulled the container image and initialised the runtime — roughly ⟨60–90⟩ s in this
system. It is billed again for a short tail after the last document, until consolidation
removes it. Both windows produce zero units at full price.

At low N that overhead spreads across a long run and barely registers. At high N the corpus
drains fast, but many nodes each pay the same fixed warm-up and each do only a few minutes of
real work. The overhead share of every billed node-hour grows and cost per document turns
back up, even though wall-clock time keeps improving. That is the whole mechanism of the
U-curve, and for scale-to-zero ephemeral workers it is the dominant cost effect.

| N | Warm-up (created → first pod ready) | Productive work | Consolidation tail | Overhead share ᴰ |
| :--- | :--- | :--- | :--- | :--- |
| ⟨low⟩ | | | | |
| ⟨high⟩ | | | | |

### 3.5 Constraint ladder

* **Tier 1** — ⟨component⟩. Proof: ⟨metric and reading⟩ ᴿ. Cost to relieve: ⟨$X⟩ ᴰ.
* **Tier 2** — ⟨component, claimed only if a new ceiling was observed after Tier 1 was actually relieved⟩. Proof: ⟨⟩ ᴿ. Cost to relieve: ⟨$⟩ ᴰ.

Sweeping concurrency relieves tiers on its own: if chunker CPU is the ceiling at N=4, then at
N=24 there are six times as many chunkers and that ceiling is gone; whatever saturates instead
is a genuinely proven second tier. This is why the sweep runs to 24 rather than stopping at 12.

The hypothesis recorded before the first run (`01-ingestion` header): the ceiling was expected
to be the Stage-1 chunker rather than TEI, because PyMuPDF extraction on a 300-page PDF is
single-threaded CPU work and may dominate embedding time by an order of magnitude, while the
original design assumed inference would saturate first. Outcome: ⟨held · inverted, stated
here verbatim⟩.

---

## 4. Cost Structure

```
Monthly cost = Floor + ( Marginal_per_unit × Volume )
                 ↑                  ↑
               §4.1          §4.2, from §3
```

### 4.1 Floor

Captured over a ⟨24 h⟩ idle window with cost attribution active, split rather than totalled.
Line-by-line audit: `00-baseline` §2 Floor.

| Block | Line | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| **B · Dedicated** | Qdrant node + gp3 volume · TEI baseline replica · Go API replica · S3 at rest · SQS | ⟨⟩ | ⟨⟩ |
| A · Shared | EKS control plane · core node group · Karpenter on Fargate · NAT · monitoring stack | ⟨⟩ | ⟨⟩ |
| **C · Total** | `A + B` | ⟨⟩ ᴰ | — |

Block B is the headline: it is what disappears from the bill if this feature is deleted. It is
not divided by an assumed number of co-tenant features — that divisor would be arbitrary, and
blocks B and C already answer both questions a reader can ask. Against its reference value:
⟨Block B vs the always-on alternative⟩ ᴱ.

*The NAT gateway* is the hidden line of this architecture class and is missing from almost
every published version of it. It is billed hourly regardless of traffic and again per
gigabyte processed — including container image pulls and the indexer's model weight downloads.

*Quantization sets the database instance class.* At 1M points × 384 dimensions, float32
vectors need 1.536 GB and INT8 needs 0.384 GB ᴰ, which is why the dedicated database line is
as small as it is. Measured Qdrant RSS at teardown: ⟨⟩ ᴿ. The retrieval cost of that
compression is not measured here.

*Article 1 advertised "$0.00 on idle."* This table states for exactly how many lines that is
true: ⟨n⟩ of ⟨m⟩. The claim was about the elastic portion of the system and reads as being
about the whole of it; both numbers are stated here rather than one quietly replacing the
other.

### 4.2 Marginal — unit economics at the sweet spot

Floor lines are excluded by definition; components sum to the total.

| Component | $/1M docs | Share |
| :--- | :--- | :--- |
| Stage-1 chunker compute | ⟨⟩ ᴰ | ⟨%⟩ |
| Stage-2 indexer compute | ⟨⟩ ᴰ | ⟨%⟩ |
| TEI serving compute attributable to ingestion | ⟨⟩ ᴰ | ⟨%⟩ |
| Warm-up and consolidation overhead (§3.4) | ⟨⟩ ᴰ | ⟨%⟩ |
| SQS requests | ⟨⟩ ᴰ | ⟨%⟩ |
| S3 requests | ⟨⟩ ᴰ | ⟨%⟩ |
| NAT data processing | ⟨⟩ ⟨ᴰ · ᴱ⟩ | ⟨%⟩ |
| **Total marginal** | ⟨⟩ ᴰ | 100 % |

### 4.3 Amortization — effective $/unit across monthly volumes

`Effective $/doc = ( Block B + Marginal × V ) ÷ V`. Arithmetic on §4.1 and §4.2, no run.

| Monthly volume | Effective $/doc ᴰ | Floor share of total |
| :--- | :--- | :--- |
| 1 000 | | |
| 10 000 | | |
| 100 000 | | |
| 1 000 000 | | |

Block B is the right floor here: for a feature on a cluster that exists anyway, the question is
what this feature costs to keep alive, not what the platform costs. Below ⟨V⟩ — the volume
where floor share drops under half — you are paying mostly for the feature to exist rather
than for work done. That volume is the lower bound of where this design makes economic sense.

### 4.4 Break-even against Fargate

The relevant alternative is not a different platform: the cluster exists regardless. It is the
compute mode for the same ingestion Jobs. Fargate removes node provisioning, per-node image
pull and Spot interruption handling entirely, and charges per vCPU-second and GB-second at a
premium over EC2 Spot. The comparison is direct because §3.1 already measured what a run
consumes.

| | Karpenter Spot (measured) | Fargate ᴰ |
| :--- | :--- | :--- |
| vCPU-hours per 1M docs | | same workload, same figure |
| GB-hours per 1M docs | | same workload, same figure |
| Warm-up overhead paid (§3.4) | | per-task cold start, no per-node image pull |
| Effective $/1M docs | | ᴰ |
| Interruption handling required | yes — the SIGTERM path in the workers | no |
| Feature floor impact | 0 at idle | 0 at idle |

**Crossover** — ⟨volume, as a number⟩. ⟨One sentence: Spot is cheaper per million documents by
X %, that discount is paid for with the interruption-handling code in the workers, and below Y
documents per month the difference is smaller than the cost of maintaining it.⟩

---

## 5. Guardrails

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Ingestion concurrency ceiling | `maxReplicaCount: ⟨⟩` | §3.3 sweet spot | `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` |
| Chunker memory limit | `limits.memory: ⟨peak + 30 %⟩` | `01-ingestion/M6` | `deploy/k8s/apps/chunker` |
| Indexer memory limit | `limits.memory: ⟨peak + 30 %⟩` | `01-ingestion/M6` | `deploy/k8s/apps/indexer` |
| Node consolidation delay | `consolidateAfter: ⟨⟩` | §3.4 overhead share | `apps-compute` NodePool |
| Max input file size | `MAX_ALLOWED_SIZE_BYTES: ⟨⟩` | §3.5 · ADR-0001 | `apps/chunker` env |
| Chunks per SQS message | `⟨⟩` | §4.2 SQS line · ADR-0004 | `apps/chunker` env |
| Ingestion backlog alert | `⟨§3.1 drain rate × alert window⟩` | §3.1 | `prometheus/rules.yaml` |
| Budget alarm | `$⟨Block B × 1.4⟩` | §4.1 | `terraform/budgets.tf` |
