# 00 · Baseline

- **Purpose** — system at rest: frozen configuration, cost attribution, price basis, floor
- **Produces** — frozen config · cost basis · metric register · floor baseline
- **Expected** — recorded 2026-08-31, before capture (`git log -S`, commit `bafdc1f`): Block B is dominated by the two Qdrant nodes and their gp3 volumes, at more than half of B; the Bedrock endpoints are second and the serving pool at minimum replicas third
- **Revision** — v1.0 (supersedes none)
- **Capture window** — 2026-09-04 18:00 → 19:00 UTC, the resting hour: `n25` drained at ~17:50, teardown began at 19:00, 6 nodes ran the full hour and `apps-compute` was at zero. The original capture hour 13:00 → 14:00 was the node-bootstrap hour (0 EC2 instances the hour before, 11 joined during it) and no longer feeds the Floor
- **Frozen at** — `cfa0ab79` · by maksimillian1. This is the commit that was live during the capture window (2026-09-03T16:19:08Z, ~20h40m before the window opened) and the last one before `15d43d5b`. `15d43d5b` (2026-09-04T13:47:53Z) lands inside the window, but it raises `maxReplicaCount` for the upcoming `n125` point and is not the state the idle hour was captured against
- **Capture notes** — anomaly: the idle-window criterion doesn't fit how this project operates (Preflight revision, 2026-09-05), because no cluster here sits idle for a full day. The one clean hour that existed was captured instead, read from CUR after the cluster had been torn down, once `01-ingestion`'s CUR pull exposed the gap. M2 fails its 5% gate (14.3%); M3 wasn't captured (cluster gone). The Floor is CUR inventory × unit rate from one resting hour, not the diurnal and monthly picture the original design wanted

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
- [x] Cost Management Preferences → split cost allocation data opted in: **EKS** enabled, measurement option **Resource requests** (2026-09-01, console; no CLI or API exists for this preference). The current console has no separate CPU-to-memory weighting control, so the line for it in an earlier draft of this checklist is removed. Once this is on, AWS computes the split-cost columns internally and nothing else needs configuring.
- [x] Kubernetes label import enabled for `app`. Like the split-cost preference, this is console-only and not part of `bcm-data-exports`' `TableConfigurations` (`get-table` lists only `TIME_GRANULARITY`, `INCLUDE_RESOURCES`, `INCLUDE_SPLIT_COST_ALLOCATION_DATA`, `INCLUDE_MANUAL_DISCOUNT_COMPATIBILITY`). Still open.
- [x] Data Exports → CUR 2.0 export created via `aws bcm-data-exports create-export`: `HOURLY`, `INCLUDE_RESOURCES=TRUE`, `INCLUDE_SPLIT_COST_ALLOCATION_DATA=TRUE`, Parquet/Parquet, `OVERWRITE_REPORT`, into `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag`. `ExportStatus: HEALTHY` (2026-09-01). First delivery pending; CUR does not backfill.

**Confirmed before the window opens**

- [x] First export file present in the bucket. Confirmed after the fact rather than by a preflight check: the first `M1` pull (2026-09-05) read real rows from this export, and both `01-ingestion` and `02-inference` later pulled from the same path.
- [x] `feature` and `tier` non-empty on EC2, EBS, SQS, S3 and endpoint rows. Confirmed after the fact through `M1`: `tier` splits EC2 cleanly into core / database / serving (Floor table), Qdrant's gp3 volumes and the two Bedrock endpoints each price as their own tagged line, and SQS and S3 match their own zero-cost rows. `feature`'s fill rate is `M2`'s number (85.7%), an aggregate over the whole window rather than the per-product-code breakdown this line asks for.
- [x] `split_line_item_*` columns present; chunker, indexer, api and tei appear as separate rows under a smoke load. Confirmed 2026-09-09 by reading the parquet directly, in hindsight rather than as a preflight step. All 11 `split_line_item_*` columns are present in the schema and populated for `AmazonEKS` rows; per-pod rows exist and are tagged down to `resource_tags['aws_eks_workload_name']`/`['aws_eks_namespace']`/`['aws_eks_node']`. Confirmed present for `api`, `tei-embeddings` and `qdrant` in this execution's own idle hour (`chunker`/`indexer` are at ~$0 here since neither runs at idle) → `./data/m12-eks-split-2026-09-04.json`. Caveat: split-cost rows lag ordinary CUR rows by several days (ordinary rows reach 2026-09-09, non-zero split rows stop at 2026-09-05T16:00Z). That doesn't affect this hour (2026-09-04), but it matters for any near-real-time re-run.
- [x] Split rows checked against their parent instance rows for double counting. Not checked row by row. Double counting is ruled out by construction: `AmazonEKS`'s split rows re-express the same `AmazonEC2` instance-hour cost, apportioned across the pods that ran on the instance by resource-request ratio, plus one `unused` remainder row per instance. They are not a second, separately billed charge. Summing a node's split rows (attributed + unused) reconstructs that node's own instance cost rather than adding to it.
- [x] Lines that cannot carry a tag enumerated → `./data/untaggable-2026-09-04.txt`, each assigned to A or B (R5). Pulled 2026-09-09: 8 non-zero product/usage-type combos, $0.21163 total (matches `M2`'s untagged figure for this hour to the cent). All 8 land in Block A (platform overhead: EKS control plane, Karpenter's Fargate pod, public IPv4, KMS). None of the untagged money belongs to Block B, so the concern in `M2`'s notes ("folding into A understates B") doesn't apply to this hour. Two of the 8 (EKS control-plane hours, the LB line) are flagged in the file as resources that are tagged but whose tag doesn't reach this CUR line. That is a narrow tagging-visibility gap rather than a structurally untaggable line, and it is worth fixing at the source instead of re-deriving from CUR each time.
- [x] M2 measured (2026-09-05, over the same 13:00–14:00Z hour as M1): **14.3%, fails the 5% gate** (Metrics table). Per K1 the A/B split is not fully trusted. It is kept because the alternative was no read at all, and because the untagged share is dominated by AWS-managed lines that can't carry a custom tag (KMS requests, public IPv4 ENI charges) rather than by gaps in this project's own tagging.

**Capture**

- [x] System frozen at a tagged commit; image digests recorded below (Configuration freeze table).
- [x] Every `M` ref confirmed against its live source and dated, or declared not done. M1/M2 confirmed 2026-09-05; M3 declared not done, because the cluster was torn down before the gap was noticed.
- [ ] Qdrant shard and replication layout read from the live collection API, not from the Helm values. Never done. The layout was read from `apps/indexer/src/haystack_pipeline.py`'s `QdrantDocumentStore(...)` call instead (Configuration freeze table), which is the code that sets it but doesn't confirm it applied. The cluster is gone, so this can't be recovered.
- [x] Rate card → `./data/price-2026-09-09.json`, pulled from the AWS Price List API: Fargate `eu-central-1` $0.04656/vCPU-hour, $0.00511/GB-hour. Bedrock `us.meta.llama3-1-8b-instruct-v1:0` on-demand $0.00022/1K input tokens, $0.00022/1K output tokens. The model is listed only in US regions (`us-east-1`/`us-east-2`/`us-west-2`), **not in eu-central-1**: the live `MODEL_ID`'s `us.` prefix is a cross-region inference profile, so a real (non-stubbed) call would leave the region. This describes the current deployment, not only the rate card, and belongs in `report.md`'s Envelope section.
- [x] Cluster identity → `./data/identity-2026-09-05.txt`: image digests, chart revisions, AMI IDs, captured just before teardown.
- [x] Idle window opened: system running and idle, API and TEI at minimum replicas, S3 event notifications disabled, **at least one full, clean UTC hour**. Revised down from "a full daily cycle" on 2026-09-05. This is a personal project, and the cluster exists only between a bootstrap and a teardown driven by whichever execution needs it next, so a multi-hour or diurnal idle capture was never going to happen. One clean hour is also CUR's resolution (`M1`'s granularity); a longer window would average more hours of the same steady state. Diurnal cost variation (for example Spot price drift by time of day) is out of scope for this report and is recorded as a limitation on the Floor figures.
- [x] Floor read no earlier than 48 h after the window closes → K3. The window closed 2026-09-04 and was re-read and revised on 2026-09-09, 4 days later (Floor). The re-read after month close is still pending; September closes in October.

### Metrics

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | idle spend per line over the idle window | CUR 2.0 parquet at `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag` · the frozen cost column (`line_item_unblended_cost`) where `line_item_line_item_type` is a usage type and `line_item_usage_start_date` falls inside the window · grouped by `line_item_product_code`, `resource_tags['user_tier']`/`['user_karpenter_sh_nodepool']`, `line_item_resource_id` · read directly with `pyarrow`; `./scripts/aws-cur-report-export.py` exists but wasn't used for this pull | confirmed 2026-09-05 | every Floor line is a group of this. The `tier` tag is what splits EC2 into core, database and serving lines; without it EC2 arrives as one number. Endpoint hours are billed per ENI per availability zone and arrive as one row per ENI |
| M2 | share of taggable idle spend arriving with no `feature` tag | same source, tag absent, denominator excludes the R5 lines | confirmed 2026-09-05: **14.3%, fails the < 5% gate** | validity gate, not a report figure. Under 5 % before the A / B split is trusted → K1. Dominated by AWS-managed lines that can't carry a custom tag (KMS request charges, per-ENI public IPv4 charges) rather than gaps in this project's own tagging. Not chased further this pass; carried as a known gate failure |
| M3 | node inventory during the idle window | `kube_node_labels` · selector on `label_karpenter_sh_nodepool` | not done: the cluster was already torn down when the gap was noticed (2026-09-05), so nothing was left to query | proof of idleness: `apps-compute` at zero for the whole window, `apps-serving` steady. Node labels are not exported by kube-state-metrics unless `--metric-labels-allowlist` includes them, and without it the query returns nothing on a healthy cluster. Approximated instead from CUR's `resource_tags['user_karpenter_sh_nodepool']` tag on the EC2 rows (Floor), a different source from the one M3 names, supporting the same claim |
| D4 | monthly floor per line | resources alive the full resting hour 2026-09-04 18:00 (CUR inventory) × unit rate × 730; EBS as size × $/GB-month; variable lines as rest-hour usage × rate × 730 | active | 730 is the AWS monthly-hour convention; the extrapolation assumes the resting hour is typical → K3 |
| R5 | allocation of untaggable lines to block A or B | hand-recorded from `./data/untaggable-2026-09-04.txt` · maksimillian1 | active | leaving these out understates a block; folding them into A by default understates B, which is the headline → K1 |

---

## 2 · Results

### Configuration freeze

System configuration params under test.

| Parameter | Value                                                                                                   | Set in                                              | Why frozen |
| :--- |:--------------------------------------------------------------------------------------------------------|:----------------------------------------------------| :--- |
| `apps-compute` instance type | `c7g` family only · sizes `xlarge`/`2xlarge`/`4xlarge` · spot only                                      | Karpenter NodePool (`deploy/k8s/platform/karpenter-resources/templates/nodepool.yaml`) | one type keeps the ingestion pool priced at one rate |
| `apps-compute` `consolidateAfter` | 30 s                                                                                                    | Karpenter NodePool                                  | the teardown tail is billed and sits inside every run window |
| `apps-serving` instance types | `instance-category In [c]`, `arch In [amd64,arm64]`, `instance-size In [xlarge,2xlarge,4xlarge]`, spot+on-demand (`deploy/k8s/platform/karpenter-resources/templates/nodepool.yaml`, 2026-09-03) | Karpenter NodePool                                  | narrowed from `[c,m,r]` to `c` only; size floor raised from unset to `xlarge` because TEI no longer fits a smaller node at its current request. Both architectures stay open on purpose: `api` runs load-test traffic on arm64 too, and `tei-embeddings` is amd64-only (`nodeSelector`, no arm64 image manifest). Unlike `apps-compute`'s single `c7g` pin, this leaves up to 6 concrete types (2 arches × 3 sizes) instead of one price, though it is much narrower than the old fully open `[c,m,r]` range |
| `apps-serving` `consolidateAfter` | 1 m                                                                                                     | Karpenter NodePool                                  | decides how much of a scale-out tail each query window carries |
| chunker requests / limits | `cpu 100m / 500m` · `mem 512Mi / 1Gi`                                                                   | `deploy/k8s/apps/chunker/scaledjob.yaml`            | sets workers per node, and split cost allocation divides a node by requests. Resized 2026-09-01 from measured p90/max CPU and memory over `ingestion-n50-test` (100-file sample). The limit keeps ~2.3x margin over the observed 433Mi max; the corpus has untested files up to 124 MB |
| indexer requests / limits | `cpu 500m / 2` · `mem 2Gi / 4Gi`                                                                        | `deploy/k8s/apps/indexer/scaledjob.yaml`            | as above; the memory limit is what every termination reading is judged against |
| Go API `minReplicaCount` | 2                                                                                                       | `api-scaler` ScaledObject                           | the always-on half of the serving Floor line |
| Go API `maxReplicaCount` | 10                                                                                                      | `api-scaler` ScaledObject                           | set above anything a sweep should reach. A run that hits it measures the ceiling instead of the system |
| Go API trigger | prometheus · `sum(rate(container_cpu_usage_seconds_total{namespace="rag-api",...}[2m]))` · threshold `0.2` · `metricType: AverageValue` | `api-scaler` ScaledObject                           | decides how many replicas appear at a given arrival rate |
| Go API requests / limits | `cpu 250m / 500m` · `mem 256Mi / 512Mi`                                                                | `deploy/k8s/apps/api/deployment.yaml`               | per-replica capacity, and the denominator every CPU reading is taken against |
| TEI `minReplicaCount` | 2                                                                                                       | `tei-embeddings-scaler` ScaledObject                | the other always-on half of the serving Floor line |
| TEI `maxReplicaCount` | 30                                                                                                      | `tei-embeddings-scaler` ScaledObject                | as above |
| TEI trigger | prometheus · `sum(rate(container_cpu_usage_seconds_total{...}[2m]))`, `metricType: AverageValue` · threshold `1.5` · `pollingInterval: 15` | `tei-embeddings-scaler` ScaledObject                | TEI is shared: the indexer drives it during ingestion and the API during queries, so this row moves figures in both executions. `sum()` rather than `avg()`, because `avg()` pinned desiredReplicas at ~1 regardless of load (2026-09-01 fix) |
| TEI requests / limits | `cpu 3 / 4` · `mem 768Mi / 1Gi`                                                                         | `deploy/k8s/platform/tei-embeddings/deployment.yaml`| per-replica capacity. CPU request raised from `2/4` on 2026-09-01 after node-level overcommit at the old 2-core request (limits measured at 171% of node allocatable under load) |
| Qdrant nodes | 2 × `r7g.large` On-Demand, `desired_size` 2 (`max_size` 3)                                              | `eks_database_nodes` (`terraform/modules/01-rag-core/eks.tf`) | the database does not autoscale on either path, so this is the one ceiling a replica change cannot relieve. Memory-optimized and not burstable: a `t` class would make each point's capacity depend on how long the cluster idled before it |
| Qdrant sharding | `shard_number` 1 (default, not set) · `replication_factor` 2                                            | `apps/indexer/src/haystack_pipeline.py` (`QdrantDocumentStore(...)`) | decides whether the second node holds data or is paid for and idle. One shard, replicated, so both nodes hold the full collection |
| Qdrant collection config | INT8 SQ on (quantile 0.99, `always_ram`) · 384 dims · sparse on · `hnsw_m`/`hnsw_ef` not set (Qdrant client default) | `apps/indexer/src/haystack_pipeline.py` (`QdrantDocumentStore(...)`), not Helm values | changes write cost, read latency and RAM together |
| Bedrock stub delay | 2000 ms                                                                                                 | `apps/api/core/domain.go` mock_delay_ms query param | every latency figure in this report is read against it |
| App pod label | `app=⟨chunker · indexer · api · tei-embeddings⟩`                                                        | every workload manifest                             | the grouping key for pod-level cost; generated Job names are not one |
| Job history retention | `successfulJobsHistoryLimit` 3 · `failedJobsHistoryLimit` 3 · `ttlSecondsAfterFinished` not set          | `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml`  | worker concurrency and termination reasons are read from Job and Pod objects, and garbage collection removes those series mid-window |
| Image digests | chunker `sha-404a267` · indexer `sha-32365dc` · api `sha-bafdc1f` · tei `cpu-1.6` (tag only, no digest pin) · qdrant `v1.18.2`. These are tags, not `sha256:` manifest digests; `./data/identity-2026-09-05.txt` | | the one thing that must not move while the config commit does · the Qdrant digest is an `arm64` manifest and the rest are `x86_64` |

### Cost basis → report §4

- **Source of record** — CUR 2.0, hourly, resource IDs and split cost allocation on, at `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag`. Every measured cost figure in this report is a sum over its rows
- **Cost column** — `line_item_unblended_cost`, used everywhere in this report. Differs from `line_item_amortized_cost` for the same node under a Savings Plan; not chosen here since none is active on this account
- **Line-item types summed** — `Usage`, `DiscountedUsage`, `SavingsPlanCoveredUsage`. Tax, credits, refunds and monthly fees are excluded: they land in an arbitrary hour and corrupt a window
- **Region and currency** — `eu-central-1` (`terraform/variables.tf`, not overridden in `terraform.tfvars`) · USD
- **Rate card** — `./data/price-2026-09-09.json`, carried only for what no run buys: Fargate vCPU-hour and GB-hour, and Bedrock per 1K input and output tokens, all read from the AWS Price List API. The Bedrock rates are consumed by `02-inference` (`E18`) and no figure in this execution uses them. Every other rate is in the CUR rows themselves, already dated
- **Spot** — priced at what was actually charged in each run hour. No historical average is frozen and none is needed
- **Reader** — `./scripts/aws-cur-report-export.py`, one window per invocation

### Envelope → report §2

- **Platform** — `eu-central-1` · EKS `1.36` (Terraform default, not verified live; the cluster is gone) · Karpenter `1.13.0` · KEDA `2.14.2` · mixed architecture: core and serving `amd64` (t3.large, c7i-flex.2xlarge at rest), database and compute `arm64` (r7g, c7g). Re-measure on any node-type or architecture change
- **Topology** — two Qdrant replicas on dedicated `r7g.large` nodes, one shard replicated across both, so each holds the full collection. 84,018 points once loaded (`01-ingestion`'s 100-file sample, identical at every point from `n50-test` through `n10`, `R21`). One cluster, no co-tenant load. Re-measure on a different replica count or shard layout
- **Autoscaling** — both serving deployments scale from 2 replicas under the triggers frozen above. Every figure in both executions is conditional on those triggers, not on a replica count. Re-measure on any trigger or threshold change
- **Egress** — S3 leaves through a gateway endpoint. Bedrock leaves through its two interface endpoints. SQS and every other AWS API call cross NAT and are billed per gigabyte
- **Generation** — stubbed at the frozen delay. No run in this report calls Bedrock
- **Floor state** — resting hour right after `n25`: collection loaded (84,018 points), ingestion pool at zero, API and TEI at 2 replicas each
- **Commercial** — the cost column and rate card above, as of 2026-09-09 (rate card date; every CUR row carries its own date already). Re-measure on any rate change
- **Outside** — multi-region, GPU inference, managed vector SaaS

### Floor → report §4.1

Resting hour 2026-09-04 18:00–19:00 UTC: `n25` drained at ~17:50, teardown began at 19:00. Six nodes ran the full hour (2 core, 2 database, 2 serving), `apps-compute` was at zero, and 2 Karpenter pods ran on Fargate. Every resource is taken from CUR for that hour; every price is unit rate × 730 h (EBS: size × $/GB-month). Variable lines are rest-hour usage × rate × 730.

| Line | Block | Resource | Rate | $/month |
| :--- | :--- | :--- | :--- | ---: |
| EKS control plane | A | 1 cluster | $0.10/h | 73.00 |
| `core-on-demand` nodes | A | 2 × t3.large On-Demand, amd64 | $0.0960/h | 140.16 |
| `core-on-demand` root EBS | A | 2 × 20 GB gp3 | $0.0952/GB-mo | 3.81 |
| Karpenter on Fargate | A | 2 pods × 0.5 vCPU / 1 GB (requests 300m / 512Mi, `karpenter.tf`) | $0.04656/vCPU-h + $0.00511/GB-h | 41.45 |
| NAT gateway | A | 1 (single NAT) | $0.052/h | 37.96 |
| Public IPv4 | A | 4 (NAT + internet-facing NLB in 3 AZs) | $0.005/h | 14.60 |
| Monitoring PVs | A | 2 × 10 GB gp3 (Prometheus, Loki; current generation) | $0.0952/GB-mo | 1.90 |
| KMS key | A | 1 | $1.00/key-month | 1.00 |
| **A fixed** | | | | **313.88** |
| `core-on-demand` cross-AZ, source unknown | A | 0.877 GiB/h (9.893 core − 9.016 ArgoCD) | $0.01/GB | 6.40 |
| NAT processing | A | 0.053 GiB/h | $0.052/GB | 2.01 |
| Other cross-AZ (NAT, Fargate, EKS ENIs) | A | 0.194 GiB/h | $0.01/GB | 1.42 |
| **A variable at rest** | | | | **9.83** |
| `database-on-demand` nodes | B | 2 × r7g.large On-Demand, arm64 | $0.1292/h | 188.63 |
| `database-on-demand` root EBS | B | 2 × 14 GB gp3 | $0.0952/GB-mo | 2.67 |
| Qdrant PVCs | B | 2 × 50 GB gp3 (`qdrant-storage-qdrant-{0,1}`; current generation) | $0.0952/GB-mo | 9.52 |
| Interface VPC endpoints | B | 2 (`bedrock`, `bedrock-runtime`) × 3 AZ | $0.012/h per ENI | 52.56 |
| `apps-serving` nodes | B | 2 × c7i-flex.2xlarge Spot, amd64, 1 TEI + 1 API each | $0.1912/h + $0.1882/h (Spot, as paid) | 276.96 |
| `apps-serving` root EBS | B | 2 × 15 GB gp3 | $0.0952/GB-mo | 2.86 |
| Load balancer (NLB behind the Gateway) | B | 1; LCU $0 at rest | $0.027/h | 19.71 |
| S3, SQS, Qdrant snapshots | B | empty buckets, idle polling | — | ~0 |
| **B fixed** | | | | **552.91** |
| Database + serving cross-AZ | B | 0.127 GiB/h | $0.01/GB | 0.93 |
| **B variable at rest** | | | | **0.93** |
| **C = A + B** | | fixed 866.79 + variable 10.76 | | **877.54** |

Left out of every total, except the `bedrock` endpoint: that one was really provisioned and really
billed, so it stays inside the as-built floor and comes out only in figure 2.

| Line | Kind | Resource | Math | $ |
| :--- | :--- | :--- | :--- | ---: |
| ArgoCD self-heal loop, cross-AZ | error | `argocd-repo-server` + `argocd-redis` (1a) → `argocd-application-controller-0` (1b), 1.35 MB/s (`./data/argocd-loop-probe-2026-09-04T1830.txt`) | 4.51 GiB/h, billed both sides = 9.02 GiB/h × $0.01 × 730 | 65.85/month |
| ArgoCD self-heal loop, T3 CPU credits | error | core node at 42% CPU against a 30% baseline; the controller alone uses 0.6 cores | 0.248 vCPU-h/h × $0.05 × 730 | 9.05/month |
| EKS control-plane logs | error | CloudWatch vended logs of `/aws/eks/simple-rag-cluster/cluster`: module default `audit, api, authenticator`, never chosen; switched off in Terraform (`enabled_log_types = []`) | 0.2195 GB/h at rest × $0.63 × 730 | 100.95/month; 2.26 spent (09-04, 09-05) |
| Orphaned PVCs | error | every launch left 2 × 50 GB Qdrant + 2 × 10 GB monitoring volumes (teardown never deleted PVCs); 35 volumes, 1,270 GB, all deleted by 2026-09-11 12:50Z | $74.88 billed (CUR, 08-01 → 09-11 02:00) + 9.84 h × 360 GB × $0.0952 / 720 | 75.35 spent; 0 now |
| Standalone EBS `simple-rag-qdrant-data` | error | 150 GB gp3 per launch, never attached; removed from Terraform 2026-09-09 | 5 volumes, 38 volume-hours billed | 0.70 spent |
| `bedrock` interface endpoint | error, inside the floor | the control-plane endpoint of the two in `vpc.tf`, reachable by nothing: the API imports only `bedrockruntime`, IAM grants only `InvokeModel*`, and the Cilium policy allows only `bedrock-runtime.*.amazonaws.com` | 1 endpoint × 3 AZ × $0.012/h × 730 | 26.28/month; figure 2 removes it (`docs/tech-debt.md` #12) |
| Cluster startup | one-time | NAT 8.86 GiB + cross-AZ 14.88 GiB, 09-04 12:00–14:00 | 8.86 × $0.052 + 14.88 × $0.01 | 0.61 per launch |

- **Serving pool idle rate** — $0.3833/h ($279.82/month ÷ 730), 09-04. The pool did not rest on the same nodes every day: 09-05 rested on c5.xlarge + c6a.xlarge at $0.18754/h (`docs/report/figures.yaml`, `serving_idle_rate_0905`), so each execution nets against its own day. `01-ingestion` does this as of 2026-09-19; `02-inference`'s Matrix still carries a retired rate
- **Untaggable lines allocated by hand** — R5, all Block A → `./data/untaggable-2026-09-04.txt`
- **Reference value** — the unqualified idle claim published in article 1. No always-on floor is carried
- **Raw data** — CUR parquet `BILLING_PERIOD=2026-09`, hour 2026-09-04 18:00; `./data/idle-2026-09-04.csv` holds the original 13:00 capture hour
- `database-on-demand` nodes are tagged `tier = "database"`, not `"database-on-demand"` (`nodes.tf:72` vs. `:112`)

### Right-sized floor (figure 2) → report §4.1

Same HA topology (2 core, 2 database, 2 serving nodes, 3 AZs, 2 Karpenter replicas). Sizes change, the 2 serving nodes are On-Demand as HA requires (`docs/tech-debt.md` #6), and the one line that is a defect rather than a size — the unreachable `bedrock` endpoint (errors table, `docs/tech-debt.md` #12) — is gone. ᴱ: priced, not run. On-Demand rates from the AWS Price List API (2026-09-11).

| Line | As built | Right-sized ᴱ | Evidence | $/month as built | $/month right-sized |
| :--- | :--- | :--- | :--- | ---: | ---: |
| Database nodes | 2 × r7g.large (2 vCPU, 16 GiB) On-Demand | 2 × c7g.large (2 vCPU, 4 GiB) On-Demand, $0.0825/h | Qdrant working set ≤ 379 MiB (M18); CPU peak 1.568 cores at r1000 keeps 2 vCPU | 188.63 | 120.45 |
| Serving nodes | 2 × c7i-flex.2xlarge Spot | 2 × c7i-flex.xlarge On-Demand, $0.1935/h; 1 API + 1 TEI on each | TEI + API ran on xlarge nodes the full hour 09-05 11:00; needs TEI requests 3/4 (HEAD has 6/8) | 276.96 | 282.51 |
| Qdrant PVCs | 2 × 50 GB gp3 | 2 × 10 GB gp3 | collection snapshot 496 MB | 9.52 | 1.90 |
| Karpenter on Fargate | 2 × 0.5 vCPU / 1 GB (request 300m) | 2 × 0.25 vCPU / 1 GB (request 250m) | controller CPU ≈ 0 at rest (probe) | 41.45 | 24.46 |
| Interface VPC endpoints | 2 × 3 AZ (`bedrock`, `bedrock-runtime`) | 1 × 3 AZ: the `bedrock` control-plane endpoint is a defect, not a size | nothing reaches it; the API imports only `bedrockruntime` (errors table) | 52.56 | 26.28 |
| Core nodes | 2 × t3.large On-Demand | unchanged | memory never measured; CPU alone would fit t3.medium | 140.16 | 140.16 |
| Everything else fixed | | unchanged | | 157.50 | 157.50 |
| **C fixed** | | | | **866.79** | **753.26** |
| Variable at rest | | unchanged | | 10.76 | 10.76 |
| **C total** | | | | **877.54** | **764.02** |

### Retro

- **Expectation** — not held. `apps-serving` is the largest B line at 50.6% ($279.82 of $552.91 fixed); Qdrant's nodes and volumes are second at 36.3% ($200.82), short of the predicted majority; the Bedrock endpoints are third at 9.5% ($52.56). Qdrant's PVC data alone is 1.7% ($9.52)
- **Attribution coverage** — `M2` fails its 5% gate at capture (14.3%) and is kept anyway per K1 (Metrics table). R5 (2026-09-09) accounts for the whole gap in dollar terms: 8 non-zero untagged lines, $0.21163, all platform overhead in Block A. That mostly explains *why* M2 is high: the lines are AWS-managed and structurally untaggable (EKS control plane, Karpenter's Fargate pod, public IPv4, KMS). The exception is two lines (EKS control-plane hours, LB usage) that are tagged but whose tag doesn't reach CUR, a narrow gap worth fixing at the source
- **Cost against estimate** — no capture-specific budget was set for this execution; not applicable
- **Month-close revision** — not yet. September closes in October, so K3's second read is still open
- **Not observed** — M3 (node inventory from Prometheus; taken from CUR instead); Qdrant hnsw config (assumed at client default, never read live); EKS control-plane version (terraform default, never read live) → report Coverage
