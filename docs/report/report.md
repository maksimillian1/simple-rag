# Executive Engineering Report — simple-rag

What asynchronous document ingestion costs, how many queries per second the retrieval
configuration sustains, and at what monthly volume the design pays for itself.

- **Report** — `simple-rag` · v1.0 · ⟨date⟩
- **System under test** — chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` · api `⟨sha256:…⟩` · commit `⟨sha⟩` · ⟨date⟩
- **Envelope** — text-layer PDF corpus, bulk drop · N ≤ ⟨max swept⟩ · R ≤ ⟨max swept⟩ req/s · EKS + Karpenter Spot, self-hosted Qdrant, TEI `bge-small-en-v1.5` · ⟨region⟩
- **Executions** — `00-baseline` · `01-ingestion` · `02-inference`
- **Raw data** — `executions/⟨…⟩/data/` · charts in `assets/`
- **Figures** — measured unless marked: ᴰ derived · ᴿ recorded · ᴱ estimated
- **Supersedes** — —
- **Changes** — first revision

Two paths, two denominators. Ingestion is priced per document, retrieval per query. No table,
chart or headline row below mixes them, and no conversion between the two is published.

---

## Coverage

| Area | Status | Evidence | Cost of absence | Since |
| :--- | :--- | :--- | :--- | :--- |
| Ingestion throughput against concurrency | measured | §3.1 · `01-ingestion` | — | v1.0 |
| Ingestion unit cost per 1M documents | derived ᴰ | §3.1 · `01-ingestion/D18` | — | v1.0 |
| Knee, sweet spot, waste boundary | measured | §3.3 | — | v1.0 |
| Warm-up share of node-hours | measured | §3.4 · `01-ingestion/D19` | — | v1.0 |
| Ingestion constraint ladder — Tier 1 | measured | §3.5 · `01-ingestion/M5` | — | v1.0 |
| Ingestion constraint ladder — Tier 2 | ⟨measured · declared, not measured⟩ | §3.5, conditional on `01-ingestion` M8–M10 | which component becomes the ceiling once the chunker is relieved, and the price of the next step | v1.0 |
| Sustained query rate at the latency target | measured | §3.6 · `02-inference/D11` | — | v1.0 |
| Query path constraint | measured | §3.7 · `02-inference/R10` | — | v1.0 |
| Retrieval cost per 1k queries — compute | derived ᴰ | §4.2 · `02-inference/D13` | — | v1.0 |
| Generation cost per 1k queries — Bedrock | estimated ᴱ | §4.2 · `02-inference/E14` | — | v1.0 |
| Idle floor, split A / B / C | measured | §4.1 · `00-baseline` §2 Floor | — | v1.0 |
| Amortization across volumes | derived ᴰ | §4.3 | — | v1.0 |
| Break-even against Fargate, ingestion | derived ᴰ | §4.4 · `01-ingestion/D22` | — | v1.0 |
| Ingest and query contention on one Qdrant node | ⟨measured · declared, not measured⟩ | §3.8 · `02-inference` second pass | whether the latency target survives a bulk ingest running underneath it, which is the state the system is actually in during a backfill | v1.0 |
| End-to-end latency including Bedrock generation | out of scope | — | the number a user experiences. It is bounded by an external quota, so it measures the provider rather than this configuration | — |
| Retrieval quality against quantization | declared, not measured | — | what INT8 compression costs in recall, and which retrieval configuration to run. INT8 SQ is a frozen given here, chosen for memory footprint | v1.1 |
| Reliability economics — Spot interruption injected under load | out of scope | — | the price of the resilience mechanism: work lost, duplicates, recovery time. Idempotency is designed in and verifiable by count comparison; pricing it needs its own run | — |
| Lambda as the build alternative | out of scope | — | a more dramatic §4.4. The cluster exists regardless, so the honest alternative is a different compute mode on the same platform | — |
| Reliability, levers and quality/cost sections | out of scope | — | template §6–§8 have no material at v1.0 and are absent rather than blank | — |
| Regression against a previous revision | out of scope | no predecessor | — | v1.1 |

---

## 1. BLUF

* **Ingestion cost at optimum** — ⟨$X / 1M docs⟩ (vs ⟨$A on Fargate, §4.4⟩) — what a million documents cost to ingest, and whether Spot beat the serverless mode
* **Sustained query rate** — ⟨R req/s at p95 = W ms⟩ (design target ⟨200⟩ ms) — how much traffic this configuration serves before latency breaks
* **Retrieval cost** — ⟨$ / 1k queries⟩ compute, plus ⟨$⟩ ᴱ generation — the two terms of a query, kept apart because one is yours and one is a vendor's
* **Idle floor, Block B** — ⟨$Y / month⟩ (vs ⟨$Z standalone, Block C⟩) — what the feature burns with zero traffic on a platform that exists anyway
* **Primary constraints** — ingestion ⟨component⟩ ᴿ · query ⟨component⟩ ᴿ — which component decides each path, and the price of the next scaling step ⟨$C⟩ ᴰ

**Verdict** — ⟨ship · ship with guardrails · do not ship⟩. ⟨One sentence, one action.⟩

---

## 2. Workload Contract & Envelope

### 2.1 Ingestion — per document

- **Unit of work** — one source document, complete when its last chunk is upserted and counted in Qdrant `points_count`
- **Workload fixture** — `⟨corpus⟩`, bulk drop · median ⟨n⟩ pages, p95 ⟨n⟩ · frozen ⟨date⟩ `⟨sha⟩` (`00-baseline` §2)
- **Denominator** — ⟨N⟩ documents, frozen with the fixture
- **Window** — opens at the first `s3:ObjectCreated`, closes at ingestion NodePool zero plus five minutes. Upload is outside the system under test

### 2.2 Query path — per query

- **Unit of work** — one search request, complete when the retrieved context is written to the response. Generation in Bedrock is outside the unit
- **Workload fixture** — ⟨query set⟩, ⟨n⟩ distinct queries replayed at a controlled arrival rate, against the collection produced by `01-ingestion`
- **Denominator** — queries served inside the steady-state window, produced by each run rather than frozen
- **Window** — opens ⟨warm-up seconds⟩ after the generator reaches the target rate, closes when the generator stops

### 2.3 Conditions shared by both

- **Envelope** — `00-baseline` §2 Envelope
- **Metric sources** — `00-baseline/metrics.md` · `01-ingestion/metrics.md` · `02-inference` §1
- **Worker packing density** — the ingestion NodePool is pinned to one instance type, giving ≈ ⟨n⟩ workers per node. Denser packing amortises warm-up across more work and shifts the sweet spot in §3.3 to the right. Every ingestion figure is conditional on this ratio
- **Scalar quantization** — INT8 SQ is a fixed parameter, chosen for memory footprint. Its effect on retrieval quality is not measured and is not claimed either way

---

## 3. Efficiency Frontier

### 3.1 Ingestion — run matrix

| N | Docs/min | Wall time | Node-hours (Spot / On-Dem) | $/run ᴰ | $/1M docs ᴰ | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | ᴿ |
| 12 | | | | | | ᴿ |
| 24 | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | ᴿ |

Excluded points and the rule applied: ⟨⟩. Config commits and per-point validity decisions are
audit trail and stay in `01-ingestion` §2.

Docs/min is measured twice from independent sources. Wall clock against the known corpus size
gives the point value; the derivative of queue depth gives the shape over time and catches a
run that stalled and recovered rather than draining steadily.

`$/run` is computed, not billed — AWS billing updates roughly daily and cannot see a
twenty-minute run. The NodePool is pinned to one instance type, so it is a product rather than
a sum over types:

```
$/run = node_hours_spot × price_spot + node_hours_on_demand × price_on_demand
```

### 3.2 Ingestion — chart

`assets/frontier-ingestion.svg`, from `executions/01-ingestion/data/frontier.csv`. Dual Y axis,
X = N. Left: docs/min, rising then flat. Right: `$/1M docs`, falling to a minimum and rising
again.

### 3.3 Ingestion — knee · sweet spot · waste boundary

| Point | How it is identified | N | Evidence |
| :--- | :--- | :--- | :--- |
| Knee | last N where docs/min still rose meaningfully — threshold ⟨⟩ | | §3.1 |
| Sweet spot | lowest `$/1M docs` | | §3.1 |
| Waste boundary | first N where `$/run` rises substantially for under 10 % throughput | | §3.1 |

⟨One sentence: the extra per document paid at the knee rather than at the sweet spot, and the
throughput given up going the other way.⟩ The guardrail in §5 is set at the sweet spot; the
knee is the documented ceiling for a hurry.

A minimum landing on the lowest or highest N swept sits on the edge of the range and is not
proven — there is no descending branch on one side of it. ⟨State whether the refinement pass
placed points on both sides.⟩

### 3.4 Shape of the ingestion cost curve

Every node is billed from provisioning but produces work only after boot, image pull and
runtime init — roughly ⟨60–90⟩ s here. It is billed again for a tail after the last document,
until consolidation removes it. Both windows produce zero units at full price.

At low N that overhead spreads across a long run and barely registers. At high N the corpus
drains fast, but many nodes each pay the same fixed warm-up and each do only a few minutes of
real work. The overhead share of every billed node-hour grows and cost per document turns back
up, even as wall-clock time keeps improving. For scale-to-zero ephemeral workers this is the
dominant cost effect.

| N | Warm-up (created → first pod ready) | Productive work | Consolidation tail | Overhead share ᴰ |
| :--- | :--- | :--- | :--- | :--- |
| ⟨low⟩ | | | | |
| ⟨high⟩ | | | | |

### 3.5 Ingestion constraint ladder

* **Tier 1** — ⟨component⟩. Proof: ⟨metric and reading⟩ ᴿ. Cost to relieve: ⟨$X⟩ ᴰ.
* **Tier 2** — ⟨claimed only if a new ceiling was observed after Tier 1 was actually relieved⟩. Proof: ⟨⟩ ᴿ. Cost to relieve: ⟨$⟩ ᴰ.

Sweeping concurrency relieves tiers on its own: if chunker CPU is the ceiling at N=4, at N=24
there are six times as many chunkers and that ceiling is gone. Whatever saturates instead is a
proven second tier. This is why the sweep runs to 24 rather than stopping at 12.

The hypothesis recorded before the first run: the ceiling was expected to be the Stage-1
chunker rather than TEI, because PyMuPDF extraction on a 300-page PDF is single-threaded CPU
work and may dominate embedding time by an order of magnitude, while the original design
assumed inference would saturate first. Outcome: ⟨held · inverted, stated here verbatim⟩.

### 3.6 Query path — run matrix

Fixed replicas, arrival rate swept. Ingestion idle unless the row says otherwise.

| Offered req/s | Served req/s | p50 ms | p95 ms | p99 ms | Error % | $/1k queries ᴰ | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| ⟨low⟩ | | | | | | | ᴿ |
| ⟨mid⟩ | | | | | | | ᴿ |
| ⟨high⟩ | | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | | ᴿ |

Offered rate and served rate are reported separately. Where they diverge the generator, not the
system, was the limit, and the row is excluded from the capacity claim.

`assets/frontier-inference.svg`, from `executions/02-inference/data/frontier.csv`. X = offered
rate, left Y = p95 latency, right Y = `$/1k queries`.

### 3.7 Query capacity and constraint

- **Sustained rate** — ⟨R⟩ req/s, the highest swept rate holding p95 under ⟨200⟩ ms with errors under ⟨0.1⟩ %
- **Reference value** — the `p95 < 200 ms` line in `architecture.md`, which was a design target and is now ⟨met · missed by ⟨n⟩ ms⟩
- **Constraint** — ⟨component⟩ ᴿ. Proof: ⟨metric and reading⟩. Relieved by ⟨replica change⟩ at ⟨$⟩ ᴰ per month

Retrieval is one gRPC round trip per query: dense, sparse and payload-text prefetch fused by
Qdrant with RRF, plus one embedding call to TEI. There is no cross-encoder and no GPU on the
path, so the ceiling is CPU on either TEI or Qdrant rather than inference hardware.

### 3.8 Contention — both paths on one Qdrant node

Qdrant serves ingestion writes and query reads from one node, so a query-load run against an
idle ingestion path measures a system nobody runs during a backfill.

| Condition | Sustained req/s | p95 ms | Δ against §3.7 |
| :--- | :--- | :--- | :--- |
| query load only | | | — |
| query load with ingestion at the §5 guardrail | | | |

⟨One sentence: what a concurrent backfill costs the latency target, and whether the guardrail
in §5 needs a second value for backfill windows.⟩

---

## 4. Cost Structure

```
Monthly cost = Floor + ( Marginal_per_doc × Docs ) + ( Marginal_per_query × Queries )
                 ↑                  ↑                            ↑
               §4.1              §4.2                          §4.2
```

### 4.1 Floor

Captured over a ⟨24 h⟩ idle window with cost attribution active, split rather than totalled.
Line-by-line audit: `00-baseline` §2 Floor.

| Block | Line | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| **B · Dedicated** | Qdrant node + gp3 volume · TEI baseline replica · Go API replica · S3 at rest · SQS | ⟨⟩ | ⟨⟩ |
| A · Shared | EKS control plane · core node group · Karpenter on Fargate · NAT · monitoring stack | ⟨⟩ | ⟨⟩ |
| **C · Total** | `A + B` | ⟨⟩ ᴰ | — |

Block B is the headline: it is what leaves the bill if the feature is deleted. It is not
divided by an assumed number of co-tenant features — that divisor would be arbitrary, and
blocks B and C already answer both questions a reader can ask. Against its reference value:
⟨Block B vs the always-on alternative⟩ ᴱ.

*The NAT gateway* is the hidden line of this architecture class and is missing from almost
every published version of it. It is billed hourly regardless of traffic, and again per
gigabyte processed, including image pulls and the indexer's model weight downloads.

*Quantization sets the database instance class.* At 1M points × 384 dimensions, float32 vectors
need 1.536 GB and INT8 needs 0.384 GB ᴰ, which is why the dedicated database line is as small
as it is. Measured Qdrant RSS at teardown: ⟨⟩ ᴿ. The retrieval cost of that compression is not
measured here.

*The query path is why two of the four B lines exist.* The TEI replica and the Go API replica
never scale to zero, because a request that arrives at zero replicas pays a cold start. §3.7
states what that permanently-on capacity buys in requests per second.

*Article 1 advertised "$0.00 on idle."* This table states for exactly how many lines that is
true: ⟨n⟩ of ⟨m⟩. The claim was about the elastic portion of the system and reads as being
about the whole of it; both numbers are stated rather than one quietly replacing the other.

### 4.2 Marginal

Floor lines are excluded by definition. Components sum to the total within each table, and the
two tables are never added together.

**Per 1M documents ingested**

| Component | $/1M docs | Share |
| :--- | :--- | :--- |
| Stage-1 chunker compute | ⟨⟩ ᴰ | ⟨%⟩ |
| Stage-2 indexer compute | ⟨⟩ ᴰ | ⟨%⟩ |
| TEI serving compute attributable to ingestion | ⟨⟩ ᴰ | ⟨%⟩ |
| Warm-up and consolidation overhead (§3.4) | ⟨⟩ ᴰ | ⟨%⟩ |
| SQS requests | ⟨⟩ ᴰ | ⟨%⟩ |
| S3 requests | ⟨⟩ ᴰ | ⟨%⟩ |
| NAT data processing | ⟨⟩ ⟨ᴰ · ᴱ⟩ | ⟨%⟩ |
| **Total** | ⟨⟩ ᴰ | 100 % |

**Per 1k queries served**

| Component | $/1k queries | Share |
| :--- | :--- | :--- |
| Go API compute above floor | ⟨⟩ ᴰ | ⟨%⟩ |
| TEI compute above floor | ⟨⟩ ᴰ | ⟨%⟩ |
| Qdrant compute above floor | ⟨⟩ ᴰ | ⟨%⟩ |
| **Retrieval total** | ⟨⟩ ᴰ | 100 % |
| Bedrock generation, at ⟨n⟩ input and ⟨n⟩ output tokens | ⟨⟩ ᴱ | — |

The retrieval total and the Bedrock line are kept apart because one is a function of this
configuration and the other is a vendor rate applied to a token count nobody swept. Context
pruning removes non-essential payload metadata before the prompt, which is what makes the
token count small enough to estimate at all.

### 4.3 Amortization

`Effective $/unit = ( Block B + Marginal × V ) ÷ V`. Arithmetic on §4.1 and §4.2, no run. Block
B is the right floor: for a feature on a cluster that exists anyway, the question is what this
feature costs to keep alive, not what the platform costs.

| Monthly documents | Effective $/doc ᴰ | Floor share |
| :--- | :--- | :--- |
| 1 000 | | |
| 10 000 | | |
| 100 000 | | |
| 1 000 000 | | |

| Monthly queries | Effective $/query ᴰ | Floor share |
| :--- | :--- | :--- |
| 10 000 | | |
| 100 000 | | |
| 1 000 000 | | |
| 10 000 000 | | |

Below ⟨V⟩ documents and ⟨V⟩ queries per month — where floor share drops under half — you are
paying mostly for the feature to exist rather than for work done. Those two volumes are the
lower bound of where this design makes economic sense. They are stated separately and never
converted into each other: the conversion needs an arrival ratio nobody measured.

### 4.4 Break-even against Fargate, ingestion only

The relevant alternative is not a different platform — the cluster exists regardless. It is the
compute mode for the same ingestion Jobs. Fargate removes node provisioning, per-node image
pull and Spot interruption handling, and charges per vCPU-second and GB-second at a premium
over EC2 Spot. The comparison is direct because §3.1 already measured what a run consumes.

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

The query path has no Fargate variant to compare against: its replicas are persistent by
design, and per-second billing buys nothing when the pod never stops.

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
| Go API replica floor | `replicas: ⟨⟩` | §3.7 sustained rate | `deploy/k8s/apps/api` |
| TEI replica floor | `replicas: ⟨⟩` | §3.7 constraint | `deploy/k8s/apps/tei` |
| Query rate alert | `⟨§3.7 sustained rate × 0.8⟩ req/s` | §3.7 | `prometheus/rules.yaml` |
| Latency SLO alert | `p95 > ⟨⟩ ms for ⟨⟩ min` | §3.7 | `prometheus/rules.yaml` |
| Backfill concurrency during query hours | `maxReplicaCount: ⟨⟩` | §3.8 | `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` |
| Ingestion backlog alert | `⟨§3.1 drain rate × alert window⟩` | §3.1 | `prometheus/rules.yaml` |
| Budget alarm | `$⟨Block B × 1.4⟩` | §4.1 | `terraform/budgets.tf` |
