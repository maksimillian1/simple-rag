# Executive Engineering Report — simple-rag

What asynchronous document ingestion costs, how many queries per second the deployment sustains,
and at what monthly volume the design pays for itself.

- **Report** — `simple-rag` · v1.0 · ⟨date⟩
- **System under test** — chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` · api `⟨sha256:…⟩` · tei `⟨sha256:…⟩` · commit `⟨sha⟩` · ⟨date⟩
- **Envelope** — text-layer PDF corpus, bulk drop · N ≤ ⟨max swept⟩ · R ≤ ⟨max swept⟩ req/s · EKS + Karpenter Spot, KEDA autoscaling from 2 replicas, self-hosted Qdrant, TEI `bge-small-en-v1.5` · ⟨region⟩
- **Executions** — `00-baseline` · `01-ingestion` · `02-inference`
- **Cost source** — AWS Cost and Usage Report 2.0, hourly, resource IDs and split cost allocation on · `⟨cost column⟩` · ⟨region⟩ · USD
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
| Ingestion cost per run | measured | §3.1 · `01-ingestion/M10` | — | v1.0 |
| Ingestion unit cost per 1M documents | derived ᴰ | §3.1 · `01-ingestion/D25` | — | v1.0 |
| Per-component share of ingestion cost | derived ᴰ | §4.2 · `01-ingestion/M12` | — | v1.0 |
| Embedding tier cost caused by ingestion | derived ᴰ | §4.2 · `01-ingestion/D23` | — | v1.0 |
| Warm-up and unused-capacity share | measured | §3.4 · `01-ingestion/D26` | — | v1.0 |
| Ingestion constraint ladder — Tier 1 | measured | §3.5 · `01-ingestion/M6` | — | v1.0 |
| Ingestion constraint ladder — Tier 2 | ⟨measured · declared, not measured⟩ | §3.5, conditional on `01-ingestion` M15–M17 | which component becomes the ceiling once the chunker is relieved, and the price of the next step | v1.0 |
| Sustained query rate at the latency target | measured | §3.7 · `02-inference/D15` | — | v1.0 |
| Replica count required at that rate | measured | §3.6 · `02-inference/M7` | — | v1.0 |
| Query path constraint | measured | §3.7 · `02-inference/R14` | — | v1.0 |
| Retrieval cost per 1k queries — marginal | derived ᴰ | §4.2 · `02-inference/D16` | — | v1.0 |
| Generation cost per 1k queries — Bedrock | estimated ᴱ | §4.2 · `02-inference/E18` | — | v1.0 |
| Behaviour above the sustained rate | out of scope | — | whether the deployment degrades or collapses under overload. Latency past capacity measures the generator's backlog, so it needs served-rate and status-code instruments and its own runs | v1.1 |
| Scaler tuning — thresholds and cooldowns | declared, not measured | — | how much of the convergence time is configuration rather than node provisioning, and what a faster trigger would cost in replica churn | v1.1 |
| Idle floor, split A / B / C | measured over ⟨24 h⟩, extrapolated ᴰ | §4.1 · `00-baseline` §2 Floor | — | v1.0 |
| Allocation of untaggable billing lines | recorded ᴿ | §4.1 · `00-baseline/R5` | — | v1.0 |
| Amortization across volumes | derived ᴰ | §4.3 | — | v1.0 |
| Break-even against Fargate, ingestion | derived ᴰ | §4.4 · `01-ingestion/D29` | — | v1.0 |
| Ingest and query contention on shared Qdrant and TEI | ⟨measured · declared, not measured⟩ | §3.8 · `02-inference` contention pass | whether the latency target survives a bulk ingest running underneath it, which is the state the system is actually in during a backfill | v1.0 |
| End-to-end latency including Bedrock generation | out of scope | — | the number a user experiences. It is bounded by an external quota, so it measures the provider rather than this configuration | — |
| Retrieval quality against quantization | declared, not measured | — | what INT8 compression costs in recall, and which retrieval configuration to run. INT8 SQ is a frozen given here, chosen for memory footprint | v1.1 |
| Reliability economics — Spot interruption injected under load | out of scope | — | the price of the resilience mechanism: work lost, duplicates, recovery time. Idempotency is designed in and verifiable by count comparison; pricing it needs its own run | — |
| Lambda as the build alternative | out of scope | — | a more dramatic §4.4. The cluster exists regardless, so the honest alternative is a different compute mode on the same platform | — |
| Reliability, levers and quality/cost sections | out of scope | — | template §6–§8 have no material at v1.0 and are absent rather than blank | — |
| Regression against a previous revision | out of scope | no predecessor | — | v1.1 |

---

## 1. BLUF

* **Ingestion cost at optimum** — ⟨$X / 1M docs⟩ ᴰ (vs ⟨$A on Fargate, §4.4⟩) — what a million documents cost to ingest, and whether Spot beat the serverless mode
* **Sustained query rate** — ⟨R req/s at p95 = W ms⟩ on ⟨n⟩ API and ⟨n⟩ TEI replicas (design target ⟨200⟩ ms) — how much traffic this deployment serves inside its latency budget, and what the autoscaler needs to get there
* **Retrieval cost** — ⟨$ / 1k queries⟩ ᴰ marginal, plus ⟨$⟩ ᴰ floor share and ⟨$⟩ ᴱ generation — three terms, kept apart because one scales with traffic, one does not, and one is a vendor's
* **Idle floor, Block B** — ⟨$Y / month⟩ ᴰ (vs ⟨$Z total, Block C⟩ ᴰ) — what the feature burns with zero traffic on a platform that exists anyway
* **Primary constraints** — ingestion ⟨component⟩ ᴿ · query ⟨component⟩ ᴿ — which component decides each path, and the price of the next scaling step ⟨$C⟩ ᴰ

**Verdict** — ⟨ship · ship with guardrails · do not ship⟩. ⟨One sentence, one action.⟩

---

## 2. Workload Contract & Envelope

### 2.1 Ingestion — per document

- **Unit of work** — one source document, complete when its last chunk is upserted and counted in Qdrant `points_count`
- **Workload fixture** — `⟨corpus⟩`, bulk drop · median ⟨n⟩ pages, p95 ⟨n⟩ · frozen ⟨date⟩ `⟨sha⟩` (`00-baseline` §2)
- **Denominator** — ⟨N⟩ documents, frozen with the fixture
- **Window** — opens at the first `s3:ObjectCreated`, closes when the ingestion pool reaches zero nodes and the embedding tier returns to its minimum, plus five minutes. Upload is outside the system under test

### 2.2 Query path — per query

- **Unit of work** — one search request, complete when the retrieved context is written to the response. Generation in Bedrock is outside the unit
- **Workload fixture** — ⟨query set⟩, ⟨n⟩ distinct queries replayed at a constant arrival rate against the collection produced by `01-ingestion`
- **Denominator** — queries served inside the steady-state window, produced by each run rather than frozen
- **Window** — opens once replicas and nodes have been stable for ⟨60⟩ s and a further ⟨60⟩ s of warm-up has elapsed; closes when the generator stops

### 2.3 Conditions shared by both

- **Envelope** — `00-baseline` §2 Envelope
- **Metric sources** — `00-baseline` §1 · `01-ingestion/metrics.md` · `02-inference` §1
- **Autoscaling** — the Go API and the embedding tier scale from two replicas each under the triggers frozen in `00-baseline` §2. Every figure in this report is conditional on those triggers rather than on a replica count, and the ceilings were set out of reach so that no run measured them
- **Shared embedding tier** — one TEI deployment serves both paths. Ingestion runs raise its replica count, and that cost is charged to ingestion in §4.2 after the always-on minimum is subtracted
- **Worker packing density** — the ingestion pool is pinned to one instance type, giving ≈ ⟨n⟩ workers per node. Denser packing amortises warm-up across more work and shifts the sweet spot in §3.3 to the right. Every ingestion figure is conditional on this ratio
- **Scalar quantization** — INT8 SQ is a fixed parameter, chosen for memory footprint. Its effect on retrieval quality is not measured and is not claimed either way

---

## 3. Efficiency Frontier

### 3.1 Ingestion — run matrix

| N | Docs/min | Wall time | TEI peak | Compute $ | TEI $ ᴰ | Other $ | $/run ᴰ | $/1M docs ᴰ | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4 | | | | | | | | | ᴿ |
| 12 | | | | | | | | | ᴿ |
| 24 | | | | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | | | | ᴿ |

Excluded points and the rule applied: ⟨⟩. Config commits and per-point validity decisions are
audit trail and stay in `01-ingestion` §2.

Docs/min is measured twice from independent sources. Wall clock against the known corpus size
gives the point value; the derivative of queue depth gives the shape over time and catches a run
that stalled and recovered rather than draining steadily.

`$/run` is billed rather than computed. The cost and usage report carries hourly line items with
sub-hour usage amounts and resource identifiers, so a twenty-minute run inside one clock hour
resolves exactly — including the minutes a node was billed before its first pod started and
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
| Knee | last N where docs/min still rose meaningfully — threshold ⟨⟩ | | §3.1 |
| Sweet spot | lowest `$/1M docs` | | §3.1 |
| Waste boundary | first N where `$/run` rises substantially for under 10 % throughput | | §3.1 |

⟨One sentence: the extra per document paid at the knee rather than at the sweet spot, and the
throughput given up going the other way.⟩ The guardrail in §5 is set at the sweet spot; the knee
is the documented ceiling for a hurry.

A minimum landing on the lowest or highest N swept sits on the edge of the range and is not
proven — there is no descending branch on one side of it. ⟨State whether the refinement pass
placed points on both sides.⟩

### 3.4 Shape of the ingestion cost curve

Every node is billed from provisioning but produces work only after boot, image pull and runtime
init. It is billed again for a tail after the last document, until consolidation removes it.
Both windows produce zero units at full price, and split cost allocation reports them directly:
capacity the bill charged for and no pod occupied.

At low N that overhead spreads across a long run and barely registers. At high N the corpus
drains fast, but many nodes each pay the same fixed warm-up and each do only a few minutes of
real work. The overhead share of every billed node-hour grows and cost per document turns back
up, even as wall-clock time keeps improving. For scale-to-zero ephemeral workers this is the
dominant cost effect.

| N | Unused capacity $ | Share of compute $ ᴰ | Warm-up interval ⟨created → first pod⟩ | Consolidation tail |
| :--- | :--- | :--- | :--- | :--- |
| ⟨low⟩ | | | | |
| ⟨high⟩ | | | | |

### 3.5 Ingestion constraint ladder

* **Tier 1** — ⟨component⟩. Proof: ⟨metric and reading⟩ ᴿ. Cost to relieve: ⟨$X⟩ ᴰ.
* **Tier 2** — ⟨claimed only if a new ceiling was observed after Tier 1 was actually relieved⟩. Proof: ⟨⟩ ᴿ. Cost to relieve: ⟨$⟩ ᴰ.

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
assumed inference would saturate first. Outcome: ⟨held · inverted, stated here verbatim⟩.

### 3.6 Query path — run matrix

Arrival rate swept. Replicas are what the autoscaler produced, not a setting.

| Offered req/s | Served req/s | api / tei replicas | Converge s | p50 ms | p95 ms | p99 ms | Error % | $/1k queries ᴰ | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 5 | | | | | | | | | ᴿ |
| 50 | | | | | | | | | ᴿ |
| 200 | | | | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | | | | ᴿ |
| ⟨refine⟩ | | | | | | | | | ᴿ |

Offered rate and served rate are reported separately. Where they diverge the generator, not the
system, was the limit, and the row is excluded from the capacity claim.

The sweep climbs from below and stops at the target rather than pushing to a throughput ceiling.
Past capacity an open-loop generator queues its own excess, and the measured p95 then grows with
the length of the run instead of describing the system. What the system does above the sustained
rate is a coverage row, not a number here.

`assets/frontier-inference.svg`, from `executions/02-inference/data/frontier.csv`. X = offered
rate, left Y = p95 latency, right Y = replicas.

### 3.7 Query capacity and constraint

- **Sustained rate** — ⟨R⟩ req/s, the highest swept rate holding p95 under ⟨200⟩ ms with errors under ⟨0.1⟩ % and served rate matching offered
- **Capacity that rate required** — ⟨n⟩ API replicas and ⟨n⟩ embedding replicas, converged in ⟨s⟩ from the minimum of two each
- **Reference value** — the `p95 < 200 ms` line in `architecture.md`, which was a design target and is now ⟨met · missed by ⟨n⟩ ms⟩
- **Constraint** — ⟨component⟩ ᴿ. Proof: ⟨metric and reading⟩. Relieved by ⟨⟩ at ⟨$⟩ ᴰ per month

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
| query load only | | | | — |
| query load with ingestion at the §5 guardrail | | | | |

⟨One sentence: what a concurrent backfill costs the latency target, whether the embedding tier
absorbed it by adding replicas or the two paths competed for the same ones, and whether the
guardrail in §5 needs a second value for backfill windows.⟩

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

Captured over a ⟨24 h⟩ idle window on a running, unloaded system, split rather than totalled.
Line-by-line audit: `00-baseline` §2 Floor. Every figure is a 24-hour measurement extrapolated
to a month ᴰ.

| Block | Line | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| **B · Dedicated** | Qdrant node + gp3 + snapshots · serving pool at 2+2 replicas · Bedrock and SQS endpoints · ECR · S3 at rest · SQS polling | ⟨⟩ ᴰ | ⟨⟩ |
| A · Shared | EKS control plane · core node group · Karpenter on Fargate · NAT · monitoring stack · shared endpoints | ⟨⟩ ᴰ | ⟨⟩ |
| **C · Total** | `A + B` | ⟨⟩ ᴰ | — |

Block B is the headline: it is what leaves the bill if the feature is deleted. It is not divided
by an assumed number of co-tenant features — that divisor would be arbitrary, and blocks B and C
already answer both questions a reader can ask. Lines that carry no resource-level tag were
assigned to a block by hand and are listed as such ᴿ; they are ⟨n⟩ % of the total.

*The NAT gateway* is the hidden line of this architecture class and is missing from almost every
published version of it. It is billed hourly regardless of traffic, and again per gigabyte
processed, including image pulls and model weight downloads. The hourly charge is floor; the
per-gigabyte charge appears again in §4.2 as a marginal line.

*Interface VPC endpoints are the second hidden line.* Each is billed per hour per availability
zone, before a byte moves. Two of them exist only for this feature.

*Quantization sets the database instance class.* At 1M points × 384 dimensions, an INT8-quantized
resident copy needs 0.384 GB against 1.536 GB for float32 ᴰ, which is why the dedicated database
line is as small as it is. The measured Qdrant working set at teardown was ⟨⟩ ᴿ, and it is an
upper bound rather than a matching figure: it includes page cache on memory-mapped segments. The
retrieval cost of that compression is not measured here.

*The query path is why the serving line exists.* Both deployments hold two replicas at zero
traffic, because a request arriving at zero replicas pays a cold start. §3.7 states what that
permanently-on capacity buys in requests per second before the autoscaler has to act.

*Article 1 advertised "$0.00 on idle."* This table states for exactly how many lines that is
true: ⟨n⟩ of ⟨m⟩. The claim was about the elastic ingestion tier and reads as being about the
whole system; both numbers are stated rather than one quietly replacing the other.

### 4.2 Marginal

Floor lines are excluded by definition. Components sum to the total within each table, and the
two tables are never added together.

**Per 1M documents ingested**

| Component | $/1M docs | Share |
| :--- | :--- | :--- |
| Stage-1 chunker pods | ⟨⟩ ᴰ | ⟨%⟩ |
| Stage-2 indexer pods | ⟨⟩ ᴰ | ⟨%⟩ |
| Embedding tier above its always-on minimum | ⟨⟩ ᴰ | ⟨%⟩ |
| Node capacity billed and occupied by no pod (§3.4) | ⟨⟩ ᴰ | ⟨%⟩ |
| SQS requests | ⟨⟩ ᴰ | ⟨%⟩ |
| S3 requests | ⟨⟩ ᴰ | ⟨%⟩ |
| NAT data processing | ⟨⟩ ᴰ | ⟨%⟩ |
| **Total** | ⟨⟩ ᴰ | 100 % |

The boundary between the pod rows is drawn by the cloud provider, not measured at either pod.
Only the instance is billed; splitting that one charge across the pods on it uses their requests
and usage against a fixed CPU-to-memory weighting. The total is exact and the internal split is
a convention — which is why the unoccupied-capacity row, which needs no convention, is the one
§3.4 argues from.

**Per 1k queries served, at the sustained rate**

| Component | $/1k queries | Share |
| :--- | :--- | :--- |
| Serving capacity above the always-on minimum | ⟨⟩ ᴰ | ⟨%⟩ |
| **Marginal total** | ⟨⟩ ᴰ | 100 % |
| Floor share at the sustained rate | ⟨⟩ ᴰ | — |
| Bedrock generation, at ⟨n⟩ input and ⟨n⟩ output tokens | ⟨⟩ ᴱ | — |

The three lines answer different questions and are not summed into a headline. The marginal
total is what an additional query costs once the tier is already scaled. The floor share assumes
the tier runs at the sustained rate continuously and is therefore a best case: at half that
utilisation it doubles. The generation line is a vendor rate applied to a token count nobody
swept, and no run called the provider. Context pruning removes non-essential payload metadata
before the prompt, which is what makes the token count small enough to estimate at all.

### 4.3 Amortization

`Effective $/unit = ( Block B + Marginal × V ) ÷ V`. Arithmetic on §4.1 and §4.2, no run. Block
B is the right floor: for a feature on a cluster that exists anyway, the question is what this
feature costs to keep alive, not what the platform costs.

**Each table below charges the whole of Block B.** They are two readings of the same floor under
two different denominators, and they are not addends: adding a `$/doc` row to a `$/query` row
counts the same monthly floor twice. The conversion that would make them additive needs an
arrival ratio nobody measured.

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
lower bound of where this design makes economic sense.

### 4.4 Break-even against Fargate, ingestion only

The relevant alternative is not a different platform — the cluster exists regardless. It is the
compute mode for the same ingestion Jobs. Fargate removes node provisioning, per-node image pull
and Spot interruption handling, and charges per vCPU-second and GB-second at a premium over EC2
Spot. The comparison is direct because §3.1 already measured what a run consumes. The embedding
tier is outside it: a shared serving deployment either way.

| | Karpenter Spot (measured) | Fargate ᴰ |
| :--- | :--- | :--- |
| vCPU-hours per 1M docs | | same workload, same figure |
| GB-hours per 1M docs | | same workload, same figure |
| Unoccupied capacity paid (§3.4) | | per-task cold start, no per-node image pull |
| Effective $/1M docs | | ᴰ |
| Interruption handling required | yes — the SIGTERM path in the workers | no |
| Feature floor impact | 0 at idle | 0 at idle |

The Fargate column is a lower bound on what Fargate would cost. No Spot capacity type exists for
it on EKS, so the comparison runs against On-Demand rates; requests are billed at the next step
of a fixed vCPU and memory grid; and each task gets its own microVM, so image pull is paid per
worker rather than amortised across a node. All three move the column up.

**Crossover** — ⟨volume, as a number⟩. ⟨One sentence: Spot is cheaper per million documents by
X %, that discount is paid for with the interruption-handling code in the workers, and below Y
documents per month the difference is smaller than the cost of maintaining it.⟩

The query path has no Fargate variant to compare against: two replicas of each deployment are
persistent by design, and per-second billing buys nothing when the pod never stops.

---

## 5. Guardrails

| Guardrail | Value | Derived from | Enforced in |
| :--- | :--- | :--- | :--- |
| Ingestion concurrency ceiling | `maxReplicaCount: ⟨⟩` | §3.3 sweet spot | `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` |
| Chunker memory limit | `limits.memory: ⟨peak + 30 %⟩` | `01-ingestion/M7`, valid only where `M8` is zero | `deploy/k8s/apps/chunker` |
| Indexer memory limit | `limits.memory: ⟨peak + 30 %⟩` | `01-ingestion/M7`, valid only where `M8` is zero | `deploy/k8s/apps/indexer` |
| Node consolidation delay | `consolidateAfter: ⟨⟩` | §3.4 unoccupied-capacity share | `apps-compute` NodePool |
| Max input file size | `MAX_ALLOWED_SIZE_BYTES: ⟨⟩` | §3.5 · ADR-0001 | `apps/chunker` env |
| Chunks per SQS message | `⟨⟩` | §4.2 SQS line · ADR-0004 | `apps/chunker` env |
| Go API replica ceiling | `maxReplicaCount: ⟨⟩` | §3.7 replicas at the sustained rate, plus margin | `api-scaler` |
| Embedding tier replica ceiling | `maxReplicaCount: ⟨⟩` | §3.7 replicas at the sustained rate, plus margin | `tei-embeddings-scaler` |
| Go API memory limit | `limits.memory: ⟨peak + 30 %⟩` | `02-inference/M6` | `deploy/k8s/apps/api` |
| Embedding tier memory limit | `limits.memory: ⟨peak + 30 %⟩` | `02-inference/M6` | `deploy/k8s/apps/tei` |
| Query rate alert | `⟨§3.7 sustained rate × 0.8⟩ req/s` | §3.7 | `prometheus/rules.yaml` |
| Latency SLO alert | `p95 > ⟨⟩ ms for ⟨⟩ min` | §3.7 | `prometheus/rules.yaml` |
| Backfill concurrency during query hours | `maxReplicaCount: ⟨⟩` | §3.8 | `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` |
| Ingestion backlog alert | `⟨§3.1 drain rate × alert window⟩` | §3.1 | `prometheus/rules.yaml` |
| Budget alarm | `$⟨Block B × 1.4⟩` | §4.1 | `terraform/budgets.tf` |
