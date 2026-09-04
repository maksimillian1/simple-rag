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

- [x] `feature` and `tier` set as provider `default_tags`.
- [x] Karpenter `EC2NodeClass.spec.tags` carries both keys on every NodePool, and instance root volumes confirmed to carry them.
- [x] EKS managed node group instances confirmed tagged through the launch template. Node group tags describe the group object, not the instances under it.
- [x] Tagged explicitly: SQS queues, S3 buckets, both Bedrock interface endpoints, the EKS cluster, the load balancer behind the Gateway.
- [x] Qdrant volumes tagged in place through the EC2 API, one per replica.
- [x] Tag values checked for case.
- [x] Every workload carries `app=⟨chunker · indexer · api · tei-embeddings⟩` as a pod label. Pod names are the split's identifier otherwise, and KEDA generates a new one per Job.
- [x] Every workload declares CPU and memory `requests`. A pod without them can be dropped from the split while the total still reconciles → K2.

**Billing console, same day** → K2

- [x] Cost allocation tags → both keys → Activate. Confirmed `aws ce list-cost-allocation-tags`: `feature` and `tier` both `Active` (2026-09-01).
- [x] Cost Management Preferences → split cost allocation data opted in: **EKS** enabled, measurement option **Resource requests** (2026-09-01, console — no CLI/API exists for this preference). No separate CPU-to-memory weighting control exists in the current console; that line in an earlier draft of this checklist didn't correspond to anything real and is removed. AWS computes the split-cost columns internally once this is on — nothing further to configure here.
- [x] Kubernetes label import enabled for `app`. Same as above: not part of `bcm-data-exports`' `TableConfigurations` (confirmed via `get-table` — only `TIME_GRANULARITY`, `INCLUDE_RESOURCES`, `INCLUDE_SPLIT_COST_ALLOCATION_DATA`, `INCLUDE_MANUAL_DISCOUNT_COMPATIBILITY` exist), a separate console-only preference — still open.
- [x] Data Exports → CUR 2.0 export created via `aws bcm-data-exports create-export`: `HOURLY`, `INCLUDE_RESOURCES=TRUE`, `INCLUDE_SPLIT_COST_ALLOCATION_DATA=TRUE`, Parquet/Parquet, `OVERWRITE_REPORT`, into `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag`. `ExportStatus: HEALTHY` (2026-09-01) — first delivery pending, CUR does not backfill.

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
| `apps-compute` instance type | `c7g` family only · sizes `xlarge`/`2xlarge`/`4xlarge` · spot only                                      | Karpenter NodePool (`deploy/k8s/platform/karpenter-resources/templates/nodepool.yaml`) | one type keeps the ingestion pool priced at one rate |
| `apps-compute` `consolidateAfter` | 30 s                                                                                                    | Karpenter NodePool                                  | the teardown tail is billed and sits inside every run window |
| `apps-serving` instance types | `instance-category In [c]`, `arch In [amd64,arm64]`, `instance-size In [xlarge,2xlarge,4xlarge]`, spot+on-demand (`deploy/k8s/platform/karpenter-resources/templates/nodepool.yaml`, 2026-09-03) | Karpenter NodePool                                  | narrowed from `[c,m,r]` to `c` only; floor raised from unset to `xlarge` since TEI no longer fits a smaller node at its current request. Arch stays open on both sides deliberately — `api` runs load-test traffic on arm64 too, `tei-embeddings` is amd64-only (`nodeSelector`, no arm64 image manifest) — so, unlike `apps-compute`'s single `c7g` pin, this bounds the pool to up to 6 concrete types (2 arches × 3 sizes) rather than pricing it as one, but replaces the previously fully open `[c,m,r]` range |
| `apps-serving` `consolidateAfter` | 1 m                                                                                                     | Karpenter NodePool                                  | decides how much of a scale-out tail each query window carries |
| chunker requests / limits | `cpu 100m / 500m` · `mem 512Mi / 1Gi`                                                                   | `deploy/k8s/apps/chunker/scaledjob.yaml`            | sets workers per node, and split cost allocation divides a node by requests. Resized 2026-09-01 from measured p90/max CPU and memory over `ingestion-n50-test` (100-file sample) — limit keeps ~2.3x margin over the observed 433Mi max, corpus has untested files up to 124 MB |
| indexer requests / limits | `cpu 500m / 2` · `mem 2Gi / 4Gi`                                                                        | `deploy/k8s/apps/indexer/scaledjob.yaml`            | as above; the memory limit is what every termination reading is judged against |
| Go API `minReplicaCount` | 2                                                                                                       | `api-scaler` ScaledObject                           | the always-on half of the serving Floor line |
| Go API `maxReplicaCount` | ⟨50⟩                                                                                                    | `api-scaler` ScaledObject                           | set above anything a sweep should reach. A run that hits it measures the ceiling instead of the system |
| Go API trigger | ⟨type⟩ · ⟨metric⟩ · threshold ⟨n⟩ ⟨confirm⟩                                                             | `api-scaler` ScaledObject                           | decides how many replicas appear at a given arrival rate |
| Go API requests / limits | ⟨cpu⟩ · ⟨mem⟩                                                                                           | `deploy/k8s/apps/api`                               | per-replica capacity, and the denominator every CPU reading is taken against |
| TEI `minReplicaCount` | 2                                                                                                       | `tei-embeddings-scaler` ScaledObject                | the other always-on half of the serving Floor line |
| TEI `maxReplicaCount` | 30                                                                                                      | `tei-embeddings-scaler` ScaledObject                | as above |
| TEI trigger | prometheus · `sum(rate(container_cpu_usage_seconds_total{...}[2m]))`, `metricType: AverageValue` · threshold `1.5` · `pollingInterval: 15` | `tei-embeddings-scaler` ScaledObject                | TEI is shared: the indexer drives it during ingestion and the API during queries, so this row moves figures in both executions. `sum()`, not `avg()` — `avg()` pinned desiredReplicas at ~1 regardless of load (2026-09-01 fix) |
| TEI requests / limits | `cpu 3 / 4` · `mem 768Mi / 1Gi`                                                                         | `deploy/k8s/platform/tei-embeddings/deployment.yaml`| per-replica capacity. Raised from `2/4` cpu request 2026-09-01 — node-level overcommit at the old 2-core request (measured 171% of node allocatable in limits under load) |
| Qdrant nodes | 2 × `r7g.large` On-Demand, `desired_size` 2 (`max_size` 3)                                              | `eks_database_nodes` (`terraform/modules/01-rag-core/eks.tf`) | the database does not autoscale on either path, so this is the one ceiling a replica change cannot relieve. Memory-optimized and not burstable: a `t` class would make each point's capacity depend on how long the cluster idled before it |
| Qdrant sharding | `shard_number` 1 (default, not set) · `replication_factor` 2                                            | `apps/indexer/src/haystack_pipeline.py` (`QdrantDocumentStore(...)`) | decides whether the second node holds data or is paid for and idle — one shard, replicated, so both nodes hold the full collection |
| Qdrant collection config | INT8 SQ on · 384 dims · sparse on · `hnsw_m` ⟨n⟩ · `hnsw_ef` ⟨n⟩                                        | Helm values                                         | changes write cost, read latency and RAM together |
| Bedrock stub delay | 2000 ms                                                                                                 | `apps/api/core/domain.go` mock_delay_ms query param | every latency figure in this report is read against it |
| App pod label | `app=⟨chunker · indexer · api · tei-embeddings⟩`                                                        | every workload manifest                             | the grouping key for pod-level cost; generated Job names are not one |
| Job history retention | `successfulJobsHistoryLimit` 3 · `failedJobsHistoryLimit` 3 · `ttlSecondsAfterFinished` not set          | `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml`  | worker concurrency and termination reasons are read from Job and Pod objects, and garbage collection removes those series mid-window |
| Image digests | chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` · api `⟨sha256:…⟩` · tei `⟨sha256:…⟩` · qdrant `⟨sha256:…⟩` |                                                     | the one thing that must not move while the config commit does · the Qdrant digest is an `arm64` manifest and the rest are `x86_64` |

### Cost basis → report §4

- **Source of record** — CUR 2.0, hourly, resource IDs and split cost allocation on, at `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag`. Every measured cost figure in this report is a sum over its rows
- **Cost column** — `⟨line_item_unblended_cost · line_item_amortized_cost⟩`, one choice, used everywhere. The two are different numbers for the same node under a Savings Plan
- **Line-item types summed** — `Usage`, `DiscountedUsage`, `SavingsPlanCoveredUsage`. Tax, credits, refunds and monthly fees are excluded: they land in an arbitrary hour and corrupt a window
- **Region and currency** — `eu-central-1` (`terraform/variables.tf`, not overridden in `terraform.tfvars`) · USD
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
| EKS control plane | A | $73.00 ᴰ | fixed |
| `core-on-demand` node group | A | $140.16 ᴰ | fixed |
| Monitoring persistent volumes — Prometheus, Loki gp3 | A | $1.90 ᴰ | fixed |
| Karpenter on Fargate | A | $20.72 ᴰ | fixed |
| NAT gateway — hourly | A | $37.96 ᴰ | fixed |
| NAT gateway — per GB at idle | A | rate $0.052/GB — needs a measured idle-window GB figure | variable |
| `database-on-demand` node group — 2 × `r7g.large` | B | $188.64 ᴰ | fixed |
| Qdrant gp3 volumes — one per replica | B | $9.52 ᴰ | fixed |
| Qdrant snapshot storage | B | rate not fixed — needs measured snapshot volume × S3 storage rate | variable |
| Interface VPC endpoints — `bedrock`, `bedrock-runtime` | B | $52.56 ᴰ | fixed |
| `apps-serving` nodes at minimum replicas — 2 API, 2 TEI | B | pinned 2026-09-03 (see Configuration freeze) — `$/month` not yet priced across the resulting up-to-6 concrete types | fixed |
| Load balancer behind the Gateway | ⟨A · B⟩ | $19.71 ᴰ base + variable LCU usage | fixed base / variable usage |
| S3 — empty bucket | B | ~$0 (negligible at empty) ᴰ | variable |
| SQS — idle scaler polling | B | ~$0 ᴰ — 2 queues × 15s polling ≈ 345k req/month, inside the 1M free tier | variable |

Priced 2026-09-02 from live AWS Pricing API (`eu-central-1`/EU Frankfurt) + repo config (cluster already destroyed by
this point — CUR delivery lags a calendar-month boundary and had nothing for the actual capture window, see Retro).
Not a CUR-sourced M1/D4 read — no idle window was ever captured before teardown. Math, D4 formula applied to list
price × count rather than measured spend:

- EKS: $0.10/h × 730h
- core-on-demand: 2 × `t3.large` × $0.096/h × 730h
- Monitoring PVs: (10Gi + 10Gi) × $0.0952/GB-mo
- Karpenter/Fargate: controller requests `300m`/`512Mi` (`terraform/modules/02-rag-k8s/karpenter.tf`) round up to Fargate's
  nearest supported pod size, `0.5 vCPU`/`1GB` → (0.5 × $0.04656 + 1 × $0.00511)/h × 730h
- NAT: single shared gateway (`single_nat_gateway=true`, `create_nat_instance` defaults `false` — confirmed, the fck-nat
  module in code isn't active) × $0.052/h × 730h
- Database: 2 × `r7g.large` × $0.1292/h × 730h
- Qdrant volumes: 2 × 50Gi × $0.0952/GB-mo
- Endpoints: `bedrock` + `bedrock-runtime`, both across all 3 private-subnet AZs → 6 ENIs × $0.012/h × 730h
- Load balancer: confirmed **NLB** (not ALB) from the Gateway's `aws-load-balancer-nlb-target-type` annotation ×
  $0.0270/h × 730h base, LCU usage not measured

- **A · Shared** — $273.74 known-fixed + NAT per-GB (unmeasured)
- **B · Dedicated** — $250.72 known-fixed + `apps-serving` (pinned, not yet priced) + Qdrant snapshots (unmeasured) → report §1 BLUF
- **C · Total** — not computable until `apps-serving`'s pinned types are priced — a real Floor line this size left open would understate C, not just leave a gap ᴰ
- **Serving pool idle rate** — ⟨$/hour⟩ ᴰ. Subtracted from every run window in both executions, so no marginal figure carries a floor line — blocked on pricing the now-pinned `apps-serving` types, not on the pinning itself
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
