# 00 · Baseline

- **Purpose** — system at rest: frozen constants, denominators, price basis, metric register, floor
- **Produces** — frozen config · price basis · metric register · floor baseline
- **Expected** — ⟨recorded ⟨date⟩, before capture⟩: Block B is dominated by the Qdrant On-Demand node and its gp3 volume; every other B line is under 10 % of B
- **Revision** — v1.0 (supersedes none)
- **Capture window** — ⟨YYYY-MM-DD HH:MM → HH:MM UTC⟩
- **Frozen at** — `⟨sha⟩` · by ⟨name⟩
- **Capture notes** — ⟨success · anomaly and how it was treated⟩

---

## 1 · Plan

### Preflight

- [ ] System frozen at a tagged commit; chunker, indexer and api image digests recorded below.
- [ ] Every `M` ref below confirmed against a live endpoint and dated.
- [ ] Every confirmed ref returns data with non-empty label dimensions under its selector.
- [ ] Cost attribution tags verified active in Terraform rather than the console. Both dimensions: `feature` and `tier`.
- [ ] Karpenter is configured to tag the nodes it creates, with both dimensions. Attribution is forward-only and never retroactive, and a controller-created resource carries no tag unless the provisioner adds it.
- [ ] Untagged share of the idle bill measured and under 5 %. Untagged spend lands in no block and silently shrinks whichever block should have carried it.
- [ ] Price basis captured → `./data/price-⟨YYYY-MM-DD⟩.json`.
- [ ] Corpus profile captured → `./data/corpus-profile.txt`.
- [ ] Query set captured → `./data/query-set.txt`.
- [ ] Cluster identity captured → `./data/identity-⟨YYYY-MM-DD⟩.txt`: image digests, chart revisions, AMI IDs.
- [ ] Idle window scheduled. It spans a full daily cycle, contains zero execution points, and runs with the S3 event notification disabled.
- [ ] Collection snapshot taken after `01-ingestion` closes → `./data/snapshot-⟨YYYY-MM-DD⟩/`. `02-inference` restores from it, so its query load runs against a known collection.

The idle window has to span a full day for two reasons. The cost backend aggregates into daily
buckets, and a window shorter than a bucket returns either nothing or a whole bucket attributed
to a fraction of it. Scheduled reconciliation, log rotation and backup jobs are floor, and they
are not spread evenly across a day.

### Metrics

Refs are cited from outside this execution as `00-baseline/M1`. Confirm every name against the
live endpoint before writing a query. A wrong name returns NO DATA, which is indistinguishable
from a missing scrape target.

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | idle spend, by service and by tier, over the idle window | Cost Explorer · daily granularity · filter `TAG:feature=simple-rag` · group by `TAG:tier` | ⟨confirmed YYYY-MM-DD⟩ | every Floor line resolves to a row of this. The `tier` dimension is what splits EC2 into `core-on-demand`, Qdrant, TEI and API; without it EC2 arrives as one number and four Floor lines cannot be filled. Both tags must be active in Terraform and in the Karpenter NodePool before the window opens |
| M2 | share of idle spend arriving with no `feature` tag | same source, tag absent | ⟨confirmed YYYY-MM-DD⟩ | validity gate, not a report figure. Gate at under 5 %, resolved before the A / B split is trusted. Untagged spend lands in neither block and silently shrinks whichever one should have carried it |
| M3 | node inventory during the idle window | `kube_node_labels` · selector on `label_karpenter_sh_nodepool` | ⟨confirmed YYYY-MM-DD⟩ | proof of idleness — `apps-compute` at zero for the whole window. Unfiltered it counts the Qdrant node as elastic capacity |

Every ref here is measured at rest. Vector memory sizing is not: both its inputs — the point
count and the resident set it is judged against — exist only after a corpus is loaded, so it
lives in `01-ingestion/D25` and `01-ingestion/M13`.

---

## 2 · Results

### Configuration freeze

| Parameter | Value | Set in | Why frozen |
| :--- | :--- | :--- | :--- |
| `apps-compute` instance type | ⟨⟩ | Karpenter NodePool | makes `$/run` a product rather than a sum over types → `01-ingestion/D19` |
| `apps-compute` `consolidateAfter` | 30 s | Karpenter NodePool | sits inside the run window by construction → `01-ingestion/K1` |
| `apps-serving` instance type | ⟨⟩ | Karpenter NodePool | fixes the cost per served request → `02-inference/D14` |
| chunker requests / limits | ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/chunker` | sets worker packing density → `01-ingestion/K2` |
| indexer requests / limits | ⟨cpu⟩ · ⟨mem 2Gi⟩ | `deploy/k8s/apps/indexer` | packing density → `01-ingestion/K2`. The memory limit is held constant across every point; the guardrail replacing it is derived at Close from `01-ingestion/M7` and `01-ingestion/M8` and lands in the next revision |
| Go API replicas · requests / limits | ⟨n⟩ · ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/api` | the query axis is arrival rate, so replicas must not move under it |
| TEI replicas · requests / limits | ⟨n⟩ · ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/tei` | a moving replica count makes the second constraint tier unattributable in both executions |
| Bedrock stub delay | ⟨n⟩ ms | `deploy/k8s/apps/api` ⟨env var⟩ | the query path is measured with generation stubbed at a fixed delay; the value sits under every p95 in `02-inference` → `02-inference/K1` |
| Qdrant collection config | INT8 SQ on · 384 dims · sparse on · `hnsw_ef` ⟨n⟩ | Helm values | changes write cost, read latency and RAM together |
| Image digests | chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` · api `⟨sha256:…⟩` | | the one thing that must not move while the config commit does |

### Input fixtures — the two denominators → report §2

The project has two denominators because it has two physically different paths. They are never
converted into each other, and no table mixes them.

**Ingestion, per document.** A unit is one source document, complete when its last chunk is
upserted and counted in Qdrant. Exact count `⟨N⟩`. Distribution: median ⟨X⟩ pages, p95 ⟨Y⟩,
total ⟨Z⟩ MB, formats ⟨pdf / md / txt split⟩. Arrival is a bulk drop: the whole corpus is
uploaded at once, not streamed. Frozen ⟨date⟩ in `./data/corpus-profile.txt`. Completeness at
each point is checked against this count by `01-ingestion/R16`.

**Query path, per query.** A unit is one search request, complete when the retrieved context is
written to the response. Generation in Bedrock is outside the unit, and no run calls Bedrock at
all: the call is stubbed at the fixed delay frozen above. The count is produced by each run
rather than frozen here. The query set is ⟨n⟩ distinct queries in `./data/query-set.txt`,
frozen ⟨date⟩.

### Price basis → report §4.3–4.4

- **Data file** — `./data/price-⟨YYYY-MM-DD⟩.json`
- **Rate type** — ⟨On-Demand list · Savings Plan · EDP⟩
- **Region and currency** — `⟨eu-central-1⟩` · USD
- **Covers** — EC2 On-Demand and Spot by type · EBS gp3 · EKS control plane · Fargate vCPU/GB · NAT hourly and per-GB · S3 storage and requests · SQS requests · Bedrock per 1K input and output tokens
- **Spot basis** — historical average over ⟨window⟩, not the instantaneous quote. Whether it matched the actual run windows is checked in `01-ingestion` Retro
- **Bedrock rates** — carried for `02-inference/E15` only. No run calls Bedrock, so this line prices an assumption rather than a measurement

### Envelope → report §2

- **Platform** — ⟨region⟩ · EKS ⟨version⟩ · Karpenter ⟨version⟩ · pinned instance types, x86_64. Re-measure on any node-type or ARM64 change
- **Scale range** — one Qdrant node, collection at ⟨n⟩ points, filled in at `01-ingestion` Close from `01-ingestion/R16`. Re-measure on sharded Qdrant or on a materially larger collection
- **Input** — the frozen corpus profile and query set above. Re-measure on a different format mix, especially the PDF share
- **Replica counts** — Go API and TEI held at the values frozen above. If `02-inference` runs its second pass, the winning count returns here as a given next revision, and the Go API and TEI Floor lines move with it
- **Generation** — stubbed. Every latency figure in `02-inference` describes the retrieval path, not an end-to-end SLO → `02-inference/K1`
- **Environment** — single-tenant cluster, no co-tenant load during any window. Re-measure on a shared cluster
- **Commercial** — ⟨rate type⟩ as of ⟨date⟩. Re-measure on any rate change
- **Outside** — multi-region, GPU inference, managed vector SaaS

### Floor → report §4.1

Captured over the idle window with attribution active. ArgoCD, Karpenter, Cilium and the
monitoring stack keep running with zero load. That is floor, not contamination: turning them
off to get a cleaner number would measure a system that does not exist.

| Line | Block | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| EKS control plane | A | ⟨73⟩ ᴰ | fixed |
| `core-on-demand` node group | A | ⟨⟩ | fixed |
| Karpenter on Fargate | A | ⟨⟩ | fixed |
| NAT gateway — hourly | A | ⟨⟩ ᴰ | fixed |
| NAT gateway — per GB | A | ⟨⟩ | variable |
| Monitoring stack — Prometheus, Loki, Grafana, EBS | A | ⟨⟩ | fixed |
| Qdrant node — On-Demand | B | ⟨⟩ | fixed |
| Qdrant gp3 volume | B | ⟨⟩ | fixed |
| TEI baseline replica | B | ⟨⟩ | fixed |
| Go API replica | B | ⟨⟩ | fixed |
| S3 — corpus at rest | B | ⟨⟩ | variable |
| SQS — idle | B | ⟨0⟩ | variable |

- **A · Shared** — ⟨$⟩
- **B · Dedicated** — ⟨$⟩ → report §1 BLUF
- **C · Total** — ⟨$⟩ ᴰ
- **Reference value** — the unqualified idle claim published in article 1
- **Raw data** — `./data/idle-⟨YYYY-MM-DD⟩.csv`

The A / B seam is decided by one question: if this feature were deleted, which lines leave the
bill? Shared cluster machinery survives. The vector database, its volume, the embedding service
and the query API do not.

Block C is `A + B`. It carries the ᴰ mark in report §4.1 and no ref: A and B are subtotals of M1
rows and have no refs either, and giving one to the sum but not to the two addends sends a
reader looking for a ref that does not exist.

There is no always-on reference value. An always-on floor prices a different tolerance for cold
start, not a different design, and comparing the two measures someone else's decision. The
comparison this report does make is against a different compute mode on the same platform, and
it sits on the marginal side: `01-ingestion/D24`.

The Qdrant node line is conditional on the instance class, and the class is confirmed in
`01-ingestion` rather than here. If `01-ingestion/D25` and `01-ingestion/M13` show it was chosen
wrongly, this baseline is re-captured in place as a new revision with its own `Supersedes`
(`methodology.md` §12). It is the only finding that propagates backwards into a closed baseline,
and Block B is the figure it moves.

### Retro

- **Expectation** — ⟨held · inverted, and which line actually dominates B⟩
- **Cost against estimate** — ⟨actual against budgeted capture cost⟩
- **Not observed** — ⟨line and why⟩ → report Coverage
- **Back into the kit** — ⟨⟩
