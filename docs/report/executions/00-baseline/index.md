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
- [ ] Every `M` ref confirmed against a live endpoint and dated in `./metrics.md`.
- [ ] Every confirmed ref returns data with non-empty label dimensions under its selector.
- [ ] Cost attribution tags verified active in Terraform rather than the console.
- [ ] Karpenter is configured to tag the nodes it creates. Attribution is forward-only and never retroactive, and a controller-created resource carries no tag unless the provisioner adds it.
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

Register in `./metrics.md`. Refs are cited from elsewhere as `00-baseline/M1`.

---

## 2 · Results

### Configuration freeze

| Parameter | Value | Set in | Why frozen |
| :--- | :--- | :--- | :--- |
| `apps-compute` instance type | ⟨⟩ | Karpenter NodePool | makes `$/run` a product rather than a sum over types → `01-ingestion/D17` |
| `apps-compute` `consolidateAfter` | 30 s | Karpenter NodePool | sits inside the run window by construction → `01-ingestion/K1` |
| `apps-serving` instance type | ⟨⟩ | Karpenter NodePool | fixes the cost per served request → `02-inference/D13` |
| chunker requests / limits | ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/chunker` | sets worker packing density → `01-ingestion/K2` |
| indexer requests / limits | ⟨cpu⟩ · ⟨mem 2Gi⟩ | `deploy/k8s/apps/indexer` | packing density; the 2 GB limit is the guardrail under test |
| Go API replicas · requests / limits | ⟨n⟩ · ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/api` | the query axis is arrival rate, so replicas must not move under it |
| TEI replicas · requests / limits | ⟨n⟩ · ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/tei` | a moving replica count makes the second constraint tier unattributable in both executions |
| Qdrant collection config | INT8 SQ on · 384 dims · sparse on · `hnsw_ef` ⟨n⟩ | Helm values | changes write cost, read latency and RAM together |
| Image digests | chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` · api `⟨sha256:…⟩` | | the one thing that must not move while the config commit does |

### Input fixtures — the two denominators → report §2

The project has two denominators because it has two physically different paths. They are never
converted into each other, and no table mixes them.

**Ingestion, per document.** A unit is one source document, complete when its last chunk is
upserted and counted in Qdrant `points_count`. Exact count `⟨N⟩`. Distribution: median ⟨X⟩
pages, p95 ⟨Y⟩, total ⟨Z⟩ MB, formats ⟨pdf / md / txt split⟩. Arrival is a bulk drop: the whole
corpus is uploaded at once, not streamed. Frozen ⟨date⟩ in `./data/corpus-profile.txt`.

**Query path, per query.** A unit is one search request, complete when the retrieved context is
written to the response. Generation in Bedrock is outside the unit, because Bedrock is an
external service under its own quota and including it would measure the provider's throttle
rather than this configuration. The count is produced by each run rather than frozen here. The
query set is ⟨n⟩ distinct queries in `./data/query-set.txt`, frozen ⟨date⟩.

### Price basis → report §4.3–4.4

- **Data file** — `./data/price-⟨YYYY-MM-DD⟩.json`
- **Rate type** — ⟨On-Demand list · Savings Plan · EDP⟩
- **Region and currency** — `⟨eu-central-1⟩` · USD
- **Covers** — EC2 On-Demand and Spot by type · EBS gp3 · EKS control plane · Fargate vCPU/GB · NAT hourly and per-GB · S3 storage and requests · SQS requests · Bedrock per 1K input and output tokens
- **Spot basis** — historical average over ⟨window⟩, not the instantaneous quote. Whether it matched the actual run windows is checked in `01-ingestion` Retro

### Envelope → report §2

- **Platform** — ⟨region⟩ · EKS ⟨version⟩ · Karpenter ⟨version⟩ · pinned instance types, x86_64. Re-measure on any node-type or ARM64 change
- **Scale range** — one Qdrant node, collection under ⟨n⟩ points. Re-measure on sharded Qdrant
- **Input** — the frozen corpus profile and query set above. Re-measure on a different format mix, especially the PDF share
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
- **C · Total** — ⟨$⟩ ᴰ, `D5`
- **Reference value** — ⟨always-on alternative⟩ ᴱ, `E7`, and the unqualified idle claim published in article 1
- **Raw data** — `./data/idle-⟨YYYY-MM-DD⟩.csv`

The A / B seam is decided by one question: if this feature were deleted, which lines leave the
bill? Shared cluster machinery survives. The vector database, its volume, the embedding service
and the query API do not.

Vector memory is sized by arithmetic, not measured: `D6`. Measured Qdrant RSS at teardown:
`R4`. The two are compared once, to confirm the instance class was not chosen wrongly.

### Retro

- **Expectation** — ⟨held · inverted, and which line actually dominates B⟩
- **Cost against estimate** — ⟨actual against budgeted capture cost⟩
- **Not observed** — ⟨line and why⟩ → report Coverage
- **Back into the kit** — ⟨⟩
