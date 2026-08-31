# 00 · Baseline

- **Purpose** — system at rest: frozen configuration, cost attribution, price basis, floor
- **Produces** — frozen config · cost basis · metric register · floor baseline
- **Expected** — ⟨recorded ⟨date⟩, before capture⟩: Block B is dominated by the two Qdrant nodes and their gp3 volumes, at more than half of B; the Bedrock endpoints are second and the serving pool at minimum replicas third
- **Revision** — v1.0 (supersedes none)
- **Capture window** — ⟨YYYY-MM-DD HH:MM → HH:MM UTC⟩
- **Frozen at** — `⟨sha⟩` · by ⟨name⟩
- **Capture notes** — ⟨success · anomaly and how it was treated⟩

---

## 1 · Plan

### Preflight

**Tagging, one `terraform apply`** → K1

- [ ] `feature` and `tier` set as provider `default_tags`.
- [ ] Karpenter `EC2NodeClass.spec.tags` carries both keys on every NodePool, and instance root volumes confirmed to carry them.
- [ ] EKS managed node group instances confirmed tagged through the launch template. Node group tags describe the group object, not the instances under it.
- [ ] Tagged explicitly: SQS queues, S3 buckets, both Bedrock interface endpoints, the EKS cluster, the load balancer behind the Gateway.
- [ ] Qdrant volumes tagged in place through the EC2 API, one per replica.
- [ ] Tag values checked for case.
- [ ] Every workload carries `component=⟨chunker · indexer · api · tei⟩` as a pod label. Pod names are the split's identifier otherwise, and KEDA generates a new one per Job.
- [ ] Every workload declares CPU and memory `requests`. A pod without them can be dropped from the split while the total still reconciles → K2.

**Billing console, same day** → K2

- [ ] Cost allocation tags → both keys → Activate.
- [ ] Cost Management Preferences → split cost allocation data opted in. Measurement option and CPU-to-memory weighting → `./data/scad-config-⟨YYYY-MM-DD⟩.txt`.
- [ ] Data Exports → CUR 2.0 export: hourly, resource IDs, split cost allocation data, Parquet, overwrite versioning, into `s3://⟨bucket⟩/⟨prefix⟩`. Kubernetes label import enabled for `component`.

**Confirmed before the window opens**

- [ ] First export file present in the bucket.
- [ ] `feature` and `tier` non-empty on EC2, EBS, SQS, S3 and endpoint rows.
- [ ] `split_line_item_*` columns present; chunker, indexer, api and tei appear as separate rows under a smoke load.
- [ ] Split rows checked against their parent instance rows for double counting.
- [ ] `./scripts/aws-cur-report-export.py --dry-run` clean against the delivered parquet.
- [ ] Lines that cannot carry a tag enumerated → `./data/untaggable-⟨YYYY-MM-DD⟩.txt`, each assigned to A or B (R5).
- [ ] M2 measured over a normal day and under 5 %.

**Capture**

- [ ] System frozen at a tagged commit; image digests recorded below.
- [ ] Every `M` ref confirmed against its live source and dated.
- [ ] Qdrant shard and replication layout read from the live collection API, not from the Helm values.
- [ ] Rate card → `./data/price-⟨YYYY-MM-DD⟩.json`.
- [ ] Cluster identity → `./data/identity-⟨YYYY-MM-DD⟩.txt`: image digests, chart revisions, AMI IDs.
- [ ] Idle window opened: system running and idle, API and TEI at minimum replicas, S3 event notifications disabled, spanning a full daily cycle.
- [ ] Floor read no earlier than 48 h after the window closes, and re-read after the month closes → K3.

### Metrics

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | idle spend per line over the idle window | CUR 2.0 parquet at `s3://⟨bucket⟩/⟨prefix⟩` · the frozen cost column where `line_item_line_item_type` is a usage type and `line_item_usage_start_date` falls inside the window · grouped by `line_item_product_code`, `tier`, `line_item_resource_id` · read by `./scripts/aws-cur-report-export.py` | ⟨confirmed YYYY-MM-DD⟩ | every Floor line is a group of this. The `tier` tag is what splits EC2 into core, database and serving lines; without it EC2 arrives as one number. Endpoint hours are billed per ENI per availability zone and arrive as one row per ENI |
| M2 | share of taggable idle spend arriving with no `feature` tag | same source, tag absent, denominator excludes the R5 lines | ⟨confirmed YYYY-MM-DD⟩ | validity gate, not a report figure. Under 5 % before the A / B split is trusted → K1 |
| M3 | node inventory during the idle window | `kube_node_labels` · selector on `label_karpenter_sh_nodepool` | ⟨confirmed YYYY-MM-DD⟩ | proof of idleness — `apps-compute` at zero for the whole window, `apps-serving` steady. Node labels are not exported by kube-state-metrics unless `--metric-labels-allowlist` includes them, and without it the query returns nothing on a healthy cluster |
| D4 | monthly floor per line | `M1 × 730 ÷ window_hours` | active | every `$/month` in the Floor table carries this mark. 730 is the AWS monthly-hour convention, and the extrapolation assumes the captured day is typical → K3 |
| R5 | allocation of untaggable lines to block A or B | hand-recorded from `./data/untaggable-⟨YYYY-MM-DD⟩.txt` · ⟨who⟩ | active | leaving these out understates a block; folding them into A by default understates B, which is the headline → K1 |

---

## 2 · Results

### Configuration freeze

The identity of the system under test. Both executions hold every row of this table constant and
cite it as one object: a change to any row invalidates points in both, whichever component it
names.

| Parameter | Value                                                                                                   | Set in                                              | Why frozen |
| :--- |:--------------------------------------------------------------------------------------------------------|:----------------------------------------------------| :--- |
| `apps-compute` instance type | ⟨⟩                                                                                                      | Karpenter NodePool                                  | one type keeps the ingestion pool priced at one rate |
| `apps-compute` `consolidateAfter` | 30 s                                                                                                    | Karpenter NodePool                                  | the teardown tail is billed and sits inside every run window |
| `apps-serving` instance types | ⟨⟩                                                                                                      | Karpenter NodePool                                  | fixes the price of the capacity both serving deployments scale into |
| `apps-serving` `consolidateAfter` | 1 m                                                                                                     | Karpenter NodePool                                  | decides how much of a scale-out tail each query window carries |
| chunker requests / limits | ⟨cpu⟩ · ⟨mem⟩                                                                                           | `deploy/k8s/apps/chunker`                           | sets workers per node, and split cost allocation divides a node by requests |
| indexer requests / limits | ⟨cpu⟩ · ⟨mem 2Gi⟩                                                                                       | `deploy/k8s/apps/indexer`                           | as above; the memory limit is what every termination reading is judged against |
| Go API `minReplicaCount` | 2                                                                                                       | `api-scaler` ScaledObject                           | the always-on half of the serving Floor line |
| Go API `maxReplicaCount` | ⟨50⟩                                                                                                    | `api-scaler` ScaledObject                           | set above anything a sweep should reach. A run that hits it measures the ceiling instead of the system |
| Go API trigger | ⟨type⟩ · ⟨metric⟩ · threshold ⟨n⟩ ⟨confirm⟩                                                             | `api-scaler` ScaledObject                           | decides how many replicas appear at a given arrival rate |
| Go API requests / limits | ⟨cpu⟩ · ⟨mem⟩                                                                                           | `deploy/k8s/apps/api`                               | per-replica capacity, and the denominator every CPU reading is taken against |
| TEI `minReplicaCount` | 2                                                                                                       | `tei-embeddings-scaler` ScaledObject                | the other always-on half of the serving Floor line |
| TEI `maxReplicaCount` | ⟨50⟩                                                                                                    | `tei-embeddings-scaler` ScaledObject                | as above |
| TEI trigger | ⟨type⟩ · ⟨metric⟩ · threshold ⟨n⟩ ⟨confirm⟩                                                             | `tei-embeddings-scaler` ScaledObject                | TEI is shared: the indexer drives it during ingestion and the API during queries, so this row moves figures in both executions |
| TEI requests / limits | ⟨cpu⟩ · ⟨mem⟩                                                                                           | `deploy/k8s/apps/tei`                               | per-replica capacity |
| Qdrant nodes | 2 × `r7g.large` On-Demand, `desired_size` 2                                                             | `eks_database_nodes`                                | the database does not autoscale on either path, so this is the one ceiling a replica change cannot relieve. Memory-optimized and not burstable: a `t` class would make each point's capacity depend on how long the cluster idled before it |
| Qdrant sharding | `shard_number` ⟨n⟩ · `replication_factor` ⟨n⟩                                                           | Helm values                                         | decides whether the second node holds data or is paid for and idle |
| Qdrant collection config | INT8 SQ on · 384 dims · sparse on · `hnsw_m` ⟨n⟩ · `hnsw_ef` ⟨n⟩                                        | Helm values                                         | changes write cost, read latency and RAM together |
| Bedrock stub delay | 2000 ms                                                                                                 | `apps/api/core/domain.go` mock_delay_ms query param | every latency figure in this report is read against it |
| Component pod label | `component=⟨chunker · indexer · api · tei⟩`                                                             | every workload manifest                             | the grouping key for pod-level cost; generated Job names are not one |
| Job history retention | `successfulJobsHistoryLimit` ⟨n⟩ · `failedJobsHistoryLimit` ⟨n⟩ · `ttlSecondsAfterFinished` ⟨n⟩         | `deploy/k8s/apps/⟨…⟩/scaledjob.yaml`                | worker concurrency and termination reasons are read from Job and Pod objects, and garbage collection removes those series mid-window |
| Image digests | chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` · api `⟨sha256:…⟩` · tei `⟨sha256:…⟩` · qdrant `⟨sha256:…⟩` |                                                     | the one thing that must not move while the config commit does · the Qdrant digest is an `arm64` manifest and the rest are `x86_64` |

### Cost basis → report §4

- **Source of record** — CUR 2.0, hourly, resource IDs and split cost allocation on, at `s3://⟨bucket⟩/⟨prefix⟩`. Every measured cost figure in this report is a sum over its rows
- **Cost column** — `⟨line_item_unblended_cost · line_item_amortized_cost⟩`, one choice, used everywhere. The two are different numbers for the same node under a Savings Plan
- **Line-item types summed** — `Usage`, `DiscountedUsage`, `SavingsPlanCoveredUsage`. Tax, credits, refunds and monthly fees are excluded: they land in an arbitrary hour and corrupt a window
- **Region and currency** — `⟨eu-central-1⟩` · USD
- **Rate card** — `./data/price-⟨YYYY-MM-DD⟩.json`, carried only for what no run buys: Fargate vCPU-hour and GB-hour, and Bedrock per 1K input and output tokens. The Bedrock rates are consumed by `02-inference` and no figure in this execution uses them. Every other rate is in the CUR rows themselves, already dated
- **Spot** — priced at what was actually charged in each run hour. No historical average is frozen and none is needed
- **Reader** — `./scripts/aws-cur-report-export.py`, one window per invocation

### Envelope → report §2

- **Platform** — ⟨region⟩ · EKS ⟨version⟩ · Karpenter ⟨version⟩ · KEDA ⟨version⟩ · mixed architecture: core-on-demand nodes `x86_64`, every other pool like db, api and jobs `arm64`. Re-measure on any node-type or architecture change
- **Topology** — two Qdrant replicas on dedicated `r7g.large` nodes, ⟨sharded · independent, collection on one⟩. One cluster, no co-tenant load. Re-measure on a different replica count or shard layout
- **Autoscaling** — both serving deployments scale from 2 replicas under the triggers frozen above. Every figure in both executions is conditional on those triggers, not on a replica count. Re-measure on any trigger or threshold change
- **Egress** — S3 leaves through a gateway endpoint. Bedrock leaves through its two interface endpoints. SQS and every other AWS API call cross NAT and are billed per gigabyte
- **Generation** — stubbed at the frozen delay. No run in this report calls Bedrock
- **Floor state** — captured against an empty collection and an idle ingestion pool. It prices the system before either execution has put anything in it
- **Commercial** — the cost column and rate card above, as of ⟨date⟩. Re-measure on any rate change
- **Outside** — multi-region, GPU inference, managed vector SaaS

### Floor → report §4.1

Captured over the idle window. Every `$/month` is D4.

Compute is priced by node pool, not by workload. Everything scheduled onto `core-on-demand` —
ArgoCD, CoreDNS, Cilium agents, Prometheus, Loki, Grafana — is already inside that one line, and
listing any of them again would count it twice. Persistent volumes are separate line items and
appear on their own.

| Line | Block | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| EKS control plane | A | ⟨⟩ ᴰ | fixed |
| `core-on-demand` node group | A | ⟨⟩ ᴰ | fixed |
| Monitoring persistent volumes — Prometheus, Loki gp3 | A | ⟨⟩ ᴰ | fixed |
| Karpenter on Fargate | A | ⟨⟩ ᴰ | fixed |
| NAT gateway — hourly | A | ⟨⟩ ᴰ | fixed |
| NAT gateway — per GB at idle | A | ⟨⟩ ᴰ | variable |
| `database-on-demand` node group — 2 × `r7g.large` | B | ⟨⟩ ᴰ | fixed |
| Qdrant gp3 volumes — one per replica | B | ⟨⟩ ᴰ | fixed |
| Qdrant snapshot storage | B | ⟨⟩ ᴰ | variable |
| Interface VPC endpoints — `bedrock`, `bedrock-runtime` | B | ⟨⟩ ᴰ | fixed |
| `apps-serving` nodes at minimum replicas — 2 API, 2 TEI | B | ⟨⟩ ᴰ | fixed |
| Load balancer behind the Gateway | ⟨A · B⟩ | ⟨⟩ ᴰ | fixed |
| S3 — empty bucket | B | ⟨⟩ ᴰ | variable |
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
