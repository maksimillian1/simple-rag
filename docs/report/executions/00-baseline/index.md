# 00 · Baseline

- **Purpose** — system at rest: frozen constants, denominators, cost basis, metric register, floor
- **Produces** — frozen config · cost attribution · rate card · metric register · floor baseline
- **Expected** — ⟨recorded ⟨date⟩, before capture⟩: Block B is dominated by the Qdrant On-Demand node and its gp3 volume; the serving pool holding four minimum replicas is second and under half of it
- **Revision** — v1.0 (supersedes none)
- **Capture window** — ⟨YYYY-MM-DD HH:MM → HH:MM UTC⟩
- **Frozen at** — `⟨sha⟩` · by ⟨name⟩
- **Capture notes** — ⟨success · anomaly and how it was treated⟩

---

## 1 · Plan

### Preflight

Three of these are forward-only and cannot be recovered afterwards: the CUR export does not
contain data from before it was created, split cost allocation does not price pods that already
exited, and a pod that declared no CPU and memory requests may be dropped from the split
entirely. Tag activation is the exception and can be backfilled.

**Applied by Terraform, in one `apply`**

- [ ] `feature` and `tier` set as provider `default_tags`.
- [ ] Karpenter `EC2NodeClass.spec.tags` carries both keys on every NodePool, and instance root volumes confirmed to inherit them.
- [ ] Resources Terraform does not reach tagged explicitly: SQS queues, S3 buckets, interface VPC endpoints, the EKS cluster, ECR repositories, the load balancer behind the Gateway.
- [ ] Qdrant volume tagged in place through the EC2 API. `StorageClass.parameters` are immutable, so `tagSpecification_1` cannot be added to the live class — it is fixed for future volumes only.
- [ ] Tag values checked for case. `Simple-rag` and `simple-rag` are two values and split every table.
- [ ] Every workload carries `component=⟨chunker · indexer · api · tei⟩` as a pod label and declares CPU and memory requests.

**Three actions in the Billing console, same day**

- [ ] Cost allocation tags → both keys selected → Activate. The keys are already listed; nothing is typed by hand.
- [ ] Cost Management Preferences → split cost allocation data opted in. The measurement option and the CPU-to-memory weighting recorded in `./data/scad-config-⟨YYYY-MM-DD⟩.txt`.
- [ ] Data Exports → CUR 2.0 export created: hourly, resource IDs, split cost allocation data, Parquet, into `s3://⟨bucket⟩/⟨prefix⟩`. Kubernetes label import enabled for `component`.

**Confirmed before the window opens**

- [ ] First export file present in the bucket.
- [ ] `resource_tags_user_feature` and `resource_tags_user_tier` non-empty on EC2, EBS, SQS, S3 and endpoint rows.
- [ ] `split_line_item_*` columns present, and chunker, indexer, api and tei appear as separate rows under a smoke load.
- [ ] `./scripts/cur-window.py --dry-run` runs against the delivered parquet without a schema error.
- [ ] Lines that cannot carry a tag enumerated → `./data/untaggable-⟨YYYY-MM-DD⟩.txt`, each assigned to A or B by hand (R5).
- [ ] Untagged share of taggable spend measured over a normal day and under 5 % (M2).

**Capture**

- [ ] System frozen at a tagged commit; image digests recorded below.
- [ ] Every `M` ref below confirmed against its live source and dated.
- [ ] Rate card captured → `./data/price-⟨YYYY-MM-DD⟩.json`.
- [ ] Corpus profile captured → `./data/corpus-profile.txt`.
- [ ] Query set captured → `./data/query-set.txt`.
- [ ] Cluster identity captured → `./data/identity-⟨YYYY-MM-DD⟩.txt`: image digests, chart revisions, AMI IDs.
- [ ] Idle window opened: the system is running and idle, not switched off. ArgoCD, Karpenter, Cilium and monitoring keep reconciling, API and TEI sit at their minimum replicas, S3 event notifications are disabled, and the window spans a full daily cycle.
- [ ] Floor read no earlier than 48 h after the window closes, and re-read after the month closes. Line items are revised until then.

### Metrics

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | idle spend per line over the idle window | CUR 2.0 parquet at `s3://⟨bucket⟩/⟨prefix⟩` · `line_item_unblended_cost` where `line_item_line_item_type='Usage'` and `line_item_usage_start_date` inside the window · grouped by `line_item_product_code`, `resource_tags_user_tier`, `line_item_resource_id` · read by `./scripts/cur-window.py` | ⟨confirmed YYYY-MM-DD⟩ | every Floor line is a group of this. The `tier` tag is what splits EC2 into `core-on-demand`, database and serving lines; without it EC2 arrives as one number. The cost column is frozen below — unblended and amortized are different numbers for the same node under a Savings Plan |
| M2 | share of taggable idle spend arriving with no `feature` tag | same source, tag column empty, denominator excludes the R5 lines | ⟨confirmed YYYY-MM-DD⟩ | validity gate, not a report figure. Under 5 % before the A / B split is trusted. Untagged spend lands in neither block and silently shrinks whichever one should have carried it |
| M3 | node inventory during the idle window | `kube_node_labels` · selector on `label_karpenter_sh_nodepool` | ⟨confirmed YYYY-MM-DD⟩ | proof of idleness — `apps-compute` at zero for the whole window, `apps-serving` steady. Node labels are not exported by kube-state-metrics unless `--metric-labels-allowlist` includes them, and without it the query returns nothing on a healthy cluster |
| D4 | monthly floor per line | `M1 × 730 ÷ window_hours` | active | every `$/month` in the Floor table carries this mark. Lines billed per GB-month arrive already prorated per hour and scale under the same arithmetic |
| R5 | allocation of untaggable lines to block A or B | hand-recorded from `./data/untaggable-⟨YYYY-MM-DD⟩.txt` · ⟨who⟩ | active | some lines carry no resource-level tag at all. Leaving them out understates a block; folding them into A by default understates B, which is the headline |

---

## 2 · Results

### Configuration freeze

| Parameter | Value | Set in | Why frozen |
| :--- | :--- | :--- | :--- |
| `apps-compute` instance type | ⟨⟩ | Karpenter NodePool | one type keeps the ingestion pool priced at one rate |
| `apps-compute` `consolidateAfter` | 30 s | Karpenter NodePool | the teardown tail is billed and sits inside every run window |
| `apps-serving` instance types | ⟨⟩ | Karpenter NodePool | fixes the price of the capacity both serving deployments scale into |
| `apps-serving` `consolidateAfter` | 1 m | Karpenter NodePool | decides how much of a scale-out tail each query window carries |
| chunker requests / limits | ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/chunker` | sets workers per node, and split cost allocation divides a node by requests |
| indexer requests / limits | ⟨cpu⟩ · ⟨mem 2Gi⟩ | `deploy/k8s/apps/indexer` | as above; the memory limit is what every termination reading is judged against |
| Go API `minReplicaCount` | 2 | `api-scaler` ScaledObject | the always-on half of the serving Floor line |
| Go API `maxReplicaCount` | ⟨50⟩ | `api-scaler` ScaledObject | set deliberately above anything the sweep should reach. A run that hits it measures the ceiling instead of the system, and is excluded |
| Go API trigger | ⟨type⟩ · ⟨metric⟩ · threshold ⟨n⟩ ⟨confirm⟩ | `api-scaler` ScaledObject | the thing that decides how many replicas appear at a given arrival rate. A change to it changes every point in `02-inference` |
| Go API requests / limits | ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/api` | per-replica capacity, and the denominator every CPU reading is taken against |
| TEI `minReplicaCount` | 2 | `tei-embeddings-scaler` ScaledObject | the other always-on half of the serving Floor line |
| TEI `maxReplicaCount` | ⟨50⟩ | `tei-embeddings-scaler` ScaledObject | as above |
| TEI trigger | ⟨type⟩ · ⟨metric⟩ · threshold ⟨n⟩ ⟨confirm⟩ | `tei-embeddings-scaler` ScaledObject | TEI is shared: the indexer drives it during ingestion and the API during queries, so this row moves figures in both executions |
| TEI requests / limits | ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/tei` | per-replica capacity |
| Component pod label | `component=⟨chunker · indexer · api · tei⟩` | every workload manifest | the grouping key for pod-level cost; generated Job names are not one |
| Job history retention | `successfulJobsHistoryLimit` ⟨n⟩ · `failedJobsHistoryLimit` ⟨n⟩ · `ttlSecondsAfterFinished` ⟨n⟩ | `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` | worker concurrency and termination reasons are read from Job and Pod objects, and garbage collection removes those series mid-window |
| Bedrock stub delay | ⟨n⟩ ms | `deploy/k8s/apps/api` ⟨env var⟩ | every latency figure in this report is read against it |
| Qdrant collection config | INT8 SQ on · 384 dims · sparse on · `hnsw_m` ⟨n⟩ · `hnsw_ef` ⟨n⟩ | Helm values | changes write cost, read latency and RAM together |
| Image digests | chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` · api `⟨sha256:…⟩` · tei `⟨sha256:…⟩` | | the one thing that must not move while the config commit does |

### Input fixtures — the two denominators → report §2

**Ingestion, per document.** A unit is one source document, complete when its last chunk is
upserted and counted in Qdrant. Exact count `⟨N⟩`. Distribution: median ⟨X⟩ pages, p95 ⟨Y⟩,
total ⟨Z⟩ MB, formats ⟨pdf / md / txt split⟩. Arrival is a bulk drop: the whole corpus is
uploaded at once, not streamed. Frozen ⟨date⟩ in `./data/corpus-profile.txt`.

**Query path, per query.** A unit is one search request, complete when the retrieved context is
written to the response. Generation is outside the unit, and no run in this report calls
Bedrock: the call is stubbed at the fixed delay frozen above. The count is produced by each run
rather than frozen here. The query set is ⟨n⟩ distinct queries in `./data/query-set.txt`,
frozen ⟨date⟩.

The two are never converted into each other, and no table mixes them.

### Cost basis → report §4

- **Source of record** — CUR 2.0, hourly, resource IDs and split cost allocation on, at `s3://⟨bucket⟩/⟨prefix⟩`. Every measured cost figure in this report is a sum over its rows
- **Cost column** — `⟨line_item_unblended_cost · line_item_amortized_cost⟩`, one choice, used everywhere
- **Region and currency** — `⟨eu-central-1⟩` · USD
- **Rate card** — `./data/price-⟨YYYY-MM-DD⟩.json`, carried only for what no run buys: Fargate vCPU-hour and GB-hour, and Bedrock per 1K input and output tokens. Every other rate is in the CUR rows themselves, already dated
- **Spot** — priced at what was actually charged in each run hour. No historical average is frozen and none is needed
- **Query file** — `./scripts/cur-window.sql`, holding the filter for each Floor line and each run window. Run locally over the parquet; no Athena scan is paid

### Envelope → report §2

- **Platform** — ⟨region⟩ · EKS ⟨version⟩ · Karpenter ⟨version⟩ · KEDA ⟨version⟩ · pinned instance types, x86_64. Re-measure on any node-type or ARM64 change
- **Scale range** — one Qdrant node. The floor is captured against an empty collection. Re-measure on sharded Qdrant
- **Input** — the corpus profile and query set frozen above. Re-measure on a different format mix, especially the PDF share
- **Autoscaling** — both serving deployments scale from 2 replicas under the triggers frozen above. Every figure in both executions is conditional on those triggers, not on a replica count. Re-measure on any trigger or threshold change
- **Generation** — stubbed at the frozen delay. Re-measure on any change to the stub
- **Environment** — single-tenant cluster, no co-tenant load during any window, and the two executions never run at the same time. Re-measure on a shared cluster
- **Commercial** — the cost column and rate card above, as of ⟨date⟩. Re-measure on any rate change
- **Outside** — multi-region, GPU inference, managed vector SaaS

### Floor → report §4.1

Captured over the idle window. Every `$/month` is D4. Line identification lives in
`./scripts/cur-window.sql`.

The serving pool line prices four pods — two API replicas and two TEI replicas — and the nodes
Karpenter keeps for them. Everything above that is caused by traffic and belongs to whichever
execution generated it.

| Line | Block | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| EKS control plane | A | ⟨⟩ ᴰ | fixed |
| `core-on-demand` node group | A | ⟨⟩ ᴰ | fixed |
| Karpenter on Fargate | A | ⟨⟩ ᴰ | fixed |
| NAT gateway — hourly | A | ⟨⟩ ᴰ | fixed |
| NAT gateway — per GB at idle | A | ⟨⟩ ᴰ | variable |
| Monitoring stack — Prometheus, Loki, Grafana, EBS | A | ⟨⟩ ᴰ | fixed |
| Interface VPC endpoints — shared | A | ⟨⟩ ᴰ | fixed |
| `database-on-demand` node — Qdrant | B | ⟨⟩ ᴰ | fixed |
| Qdrant gp3 volume | B | ⟨⟩ ᴰ | fixed |
| Qdrant snapshot storage | B | ⟨⟩ ᴰ | variable |
| `apps-serving` nodes at minimum replicas — 2 API, 2 TEI | B | ⟨⟩ ᴰ | fixed |
| Interface VPC endpoint — Bedrock | B | ⟨⟩ ᴰ | fixed |
| Interface VPC endpoint — SQS | B | ⟨⟩ ᴰ | fixed |
| Load balancer behind the Gateway | ⟨A · B⟩ | ⟨⟩ ᴰ | fixed |
| ECR storage — application images | B | ⟨⟩ ᴰ | variable |
| S3 — corpus at rest | B | ⟨⟩ ᴰ | variable |
| SQS — idle scaler polling | B | ⟨⟩ ᴰ | variable |

- **A · Shared** — ⟨$⟩
- **B · Dedicated** — ⟨$⟩ → report §1 BLUF
- **C · Total** — ⟨$⟩ ᴰ
- **Serving pool idle rate** — ⟨$/hour⟩ ᴰ. Subtracted from every run window in both executions, so no marginal figure carries a floor line
- **Untaggable lines allocated by hand** — R5, ⟨$⟩ of ⟨$⟩ total
- **Reference value** — the unqualified idle claim published in article 1. No always-on floor is carried: it prices a different tolerance for cold start rather than a different design
- **Raw data** — `./data/idle-⟨YYYY-MM-DD⟩.csv`

### Retro

- **Expectation** — ⟨held · inverted, and which line actually dominates B⟩
- **Attribution coverage** — ⟨M2 at capture, and which lines needed R5⟩
- **Cost against estimate** — ⟨actual against budgeted capture cost⟩
- **Month-close revision** — ⟨did any line move between the 48 h read and the closed month⟩
- **Not observed** — ⟨line and why⟩ → report Coverage
- **Back into the kit** — ⟨⟩
