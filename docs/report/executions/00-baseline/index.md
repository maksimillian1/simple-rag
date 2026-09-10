# 00 · Baseline

- **Purpose** — system at rest: frozen configuration, cost attribution, price basis, floor
- **Produces** — frozen config · cost basis · metric register · floor baseline
- **Expected** — recorded 2026-08-31, before capture (`git log -S`, commit `bafdc1f`): Block B is dominated by the two Qdrant nodes and their gp3 volumes, at more than half of B; the Bedrock endpoints are second and the serving pool at minimum replicas third
- **Revision** — v1.0 (supersedes none)
- **Capture window** — 2026-09-04 13:00 → 14:00 UTC. Cluster created 12:36:18Z, `n125` opened 14:00:58Z. Not idle by the original criterion — kept anyway, see Floor notes. This is the node-bootstrap hour, not a settled idle hour: 0 EC2 instances existed the hour before, 11 join and pull images during this one
- **Frozen at** — `cfa0ab79` · by maksimillian1 — the commit actually live during the capture window: 2026-09-03T16:19:08Z, ~20h40m before the window opened, and the last one before `15d43d5b` (2026-09-04T13:47:53Z, inside the window itself but a config change *for* the upcoming `n125` point — raising `maxReplicaCount` — not the state the idle hour was captured against)
- **Capture notes** — anomaly: the idle-window criterion itself didn't survive contact with how this project actually operates (Preflight revision, 2026-09-05) — no cluster was ever going to sit idle for a full day just to satisfy it. Captured the one clean hour that existed instead, after the cluster had already been torn down and the gap was noticed from `01-ingestion`'s own CUR pull. M2 fails its 5% gate (14.3%); M3 wasn't captured at all (cluster gone). Floor numbers are real CUR reads, not list-price math, for the first time — but from one hour, not the diurnal/monthly picture the original design wanted

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

- [x] First export file present in the bucket. Confirmed retroactively, not via a dedicated preflight check — the first `M1` pull (2026-09-05) read real rows from this export, and both `01-ingestion` and `02-inference` later pulled successfully from the same path.
- [x] `feature` and `tier` non-empty on EC2, EBS, SQS, S3 and endpoint rows. Confirmed retroactively via `M1`: `tier` splits EC2 cleanly into core / database / serving (Floor table below), Qdrant's gp3 volumes and the two Bedrock endpoints each price as their own tagged line, SQS and S3 both confirmed against their own (zero-cost) rows. `feature`'s fill rate is `M2`'s number below (85.7%) — an aggregate across the whole window, not broken out per product code the way this line asks.
- [x] `split_line_item_*` columns present; chunker, indexer, api and tei appear as separate rows under a smoke load. Confirmed 2026-09-09 by reading the parquet directly (not through this checklist's own preflight step — done in hindsight, months after the window). All 11 `split_line_item_*` columns are present in the schema and populated for `AmazonEKS` rows; per-pod rows exist and are tagged down to `resource_tags['aws_eks_workload_name']`/`['aws_eks_namespace']`/`['aws_eks_node']`. Confirmed present for `api`, `tei-embeddings` and `qdrant` in this execution's own idle hour (`chunker`/`indexer` are at ~$0 here since neither runs at idle) → `./data/m12-eks-split-2026-09-04.json`. One caveat found alongside: split-cost rows lag ordinary CUR rows by several days (ordinary rows reach 2026-09-09, non-zero split rows stop at 2026-09-05T16:00Z) — irrelevant for this hour (2026-09-04) but relevant if this is ever re-run near-real-time.
- [x] Split rows checked against their parent instance rows for double counting. Not literally checked row-by-row, but the mechanism is now understood well enough to rule out double counting by construction: `AmazonEKS`'s split rows are AWS's own re-expression of the same `AmazonEC2` instance-hour cost, apportioned across the pods that ran on it by resource-request ratio, plus one `unused` remainder row per instance — not a second, separately-billed charge. Summing a node's split rows (attributed + unused) reconstructs that node's own instance cost rather than adding to it.
- [x] Lines that cannot carry a tag enumerated → `./data/untaggable-2026-09-04.txt`, each assigned to A or B (R5). Pulled 2026-09-09: 8 non-zero product/usage-type combos, $0.21163 total (matches `M2`'s untagged figure for this hour to the cent). All 8 land in Block A (platform overhead — EKS control plane, Karpenter's own Fargate pod, public IPv4, KMS); nothing untagged turned out to be Block B money, so the concern `M2`'s notes raised ("folding into A understates B") doesn't bite for this particular hour. Two of the 8 (EKS control-plane hours, the LB line) are flagged in the file as resources that ARE tagged but don't carry it through to this CUR line — a narrow, real tagging-visibility gap, not a structurally-untaggable one; worth fixing at the source later rather than re-deriving from CUR each time.
- [x] M2 measured (2026-09-05, over the same 13:00–14:00Z hour as M1) — **14.3%, fails the 5% gate** (see Metrics table). A/B split below is not fully trusted per K1; kept anyway since the alternative was no read at all, and the untagged share is dominated by AWS-managed lines that can't carry a custom tag (KMS requests, public IPv4 ENI charges) rather than a tagging gap in this project's own resources.

**Capture**

- [x] System frozen at a tagged commit; image digests recorded below (Configuration freeze table).
- [x] Every `M` ref confirmed against its live source and dated, or declared not done — M1/M2 confirmed 2026-09-05; M3 declared not done, cluster torn down before the gap was noticed.
- [ ] Qdrant shard and replication layout read from the live collection API, not from the Helm values. Never done — read from `apps/indexer/src/haystack_pipeline.py`'s `QdrantDocumentStore(...)` call instead (Configuration freeze table), which is the code that sets it, not a live confirmation that it applied. Cluster is gone; not recoverable.
- [x] Rate card → `./data/price-2026-09-09.json`. Pulled from the AWS Price List API (not memory/guesswork): Fargate `eu-central-1` $0.04656/vCPU-hour, $0.00511/GB-hour. Bedrock `us.meta.llama3-1-8b-instruct-v1:0` on-demand $0.00022/1K input tokens, $0.00022/1K output tokens — found only in US regions (`us-east-1`/`us-east-2`/`us-west-2`), **not eu-central-1 at all**: the live `MODEL_ID`'s `us.` prefix is a cross-region inference profile, so a real (non-stubbed) call would leave the region entirely. That's a real fact about the current deployment, not just a rate-card footnote — worth carrying into `report.md`'s Envelope section.
- [x] Cluster identity → `./data/identity-2026-09-05.txt`: image digests, chart revisions, AMI IDs — captured just before teardown.
- [x] Idle window opened: system running and idle, API and TEI at minimum replicas, S3 event notifications disabled, **at least one full, clean UTC hour** — revised down from "a full daily cycle" (2026-09-05): this is a personal project, not a service kept running idle on a schedule; the cluster only exists between a bootstrap and a teardown driven by whatever execution needs it next, so a multi-hour or diurnal idle capture was never going to happen in practice. One clean hour is what CUR can actually resolve anyway (`M1`'s own granularity) — a longer window would average across more hours of the same steady state, not measure something a single hour can't. Diurnal cost variation (e.g. spot price drift by time of day) is out of scope for this report; note it as a limitation on the Floor figures below instead of chasing it.
- [x] Floor read no earlier than 48 h after the window closes → K3 — window closed 2026-09-04, re-read and revised 2026-09-09 (4 days later, see Floor notes). Re-read after the month closes: not yet — September doesn't close until October.

### Metrics

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | idle spend per line over the idle window | CUR 2.0 parquet at `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag` · the frozen cost column (`line_item_unblended_cost`) where `line_item_line_item_type` is a usage type and `line_item_usage_start_date` falls inside the window · grouped by `line_item_product_code`, `resource_tags['user_tier']`/`['user_karpenter_sh_nodepool']`, `line_item_resource_id` · read directly via `pyarrow`, not yet through `./scripts/aws-cur-report-export.py` (script exists but wasn't used for this pull) | confirmed 2026-09-05 | every Floor line is a group of this. The `tier` tag is what splits EC2 into core, database and serving lines; without it EC2 arrives as one number. Endpoint hours are billed per ENI per availability zone and arrive as one row per ENI |
| M2 | share of taggable idle spend arriving with no `feature` tag | same source, tag absent, denominator excludes the R5 lines | confirmed 2026-09-05 — **14.3%, fails the < 5% gate** | validity gate, not a report figure. Under 5 % before the A / B split is trusted → K1. Dominated by AWS-managed lines that can't carry a custom tag (KMS request charges, per-ENI public IPv4 charges) rather than a gap in this project's own tagging — not re-chased this pass, carried as a known gate failure |
| M3 | node inventory during the idle window | `kube_node_labels` · selector on `label_karpenter_sh_nodepool` | not done — cluster was already torn down by the time this gap was noticed (2026-09-05); nothing left to query live | proof of idleness — `apps-compute` at zero for the whole window, `apps-serving` steady. Node labels are not exported by kube-state-metrics unless `--metric-labels-allowlist` includes them, and without it the query returns nothing on a healthy cluster. Approximated instead from CUR's own `resource_tags['user_karpenter_sh_nodepool']` tag on the EC2 rows themselves (Floor notes above) — not the same source M3 names, but the same claim |
| D4 | monthly floor per line | `M1 × 730 ÷ window_hours` | active | every `$/month` in the Floor table carries this mark. 730 is the AWS monthly-hour convention, and the extrapolation assumes the captured day is typical → K3 |
| R5 | allocation of untaggable lines to block A or B | hand-recorded from `./data/untaggable-2026-09-04.txt` · maksimillian1 | active | leaving these out understates a block; folding them into A by default understates B, which is the headline → K1 |

---

## 2 · Results

### Configuration freeze

The identity of the system under test. Both [01-ingestion](..%2F01-ingestion) and [02-inference](..%2F02-inference) rely on it.

| Parameter | Value                                                                                                   | Set in                                              | Why frozen |
| :--- |:--------------------------------------------------------------------------------------------------------|:----------------------------------------------------| :--- |
| `apps-compute` instance type | `c7g` family only · sizes `xlarge`/`2xlarge`/`4xlarge` · spot only                                      | Karpenter NodePool (`deploy/k8s/platform/karpenter-resources/templates/nodepool.yaml`) | one type keeps the ingestion pool priced at one rate |
| `apps-compute` `consolidateAfter` | 30 s                                                                                                    | Karpenter NodePool                                  | the teardown tail is billed and sits inside every run window |
| `apps-serving` instance types | `instance-category In [c]`, `arch In [amd64,arm64]`, `instance-size In [xlarge,2xlarge,4xlarge]`, spot+on-demand (`deploy/k8s/platform/karpenter-resources/templates/nodepool.yaml`, 2026-09-03) | Karpenter NodePool                                  | narrowed from `[c,m,r]` to `c` only; floor raised from unset to `xlarge` since TEI no longer fits a smaller node at its current request. Arch stays open on both sides deliberately — `api` runs load-test traffic on arm64 too, `tei-embeddings` is amd64-only (`nodeSelector`, no arm64 image manifest) — so, unlike `apps-compute`'s single `c7g` pin, this bounds the pool to up to 6 concrete types (2 arches × 3 sizes) rather than pricing it as one, but replaces the previously fully open `[c,m,r]` range |
| `apps-serving` `consolidateAfter` | 1 m                                                                                                     | Karpenter NodePool                                  | decides how much of a scale-out tail each query window carries |
| chunker requests / limits | `cpu 100m / 500m` · `mem 512Mi / 1Gi`                                                                   | `deploy/k8s/apps/chunker/scaledjob.yaml`            | sets workers per node, and split cost allocation divides a node by requests. Resized 2026-09-01 from measured p90/max CPU and memory over `ingestion-n50-test` (100-file sample) — limit keeps ~2.3x margin over the observed 433Mi max, corpus has untested files up to 124 MB |
| indexer requests / limits | `cpu 500m / 2` · `mem 2Gi / 4Gi`                                                                        | `deploy/k8s/apps/indexer/scaledjob.yaml`            | as above; the memory limit is what every termination reading is judged against |
| Go API `minReplicaCount` | 2                                                                                                       | `api-scaler` ScaledObject                           | the always-on half of the serving Floor line |
| Go API `maxReplicaCount` | 10                                                                                                      | `api-scaler` ScaledObject                           | set above anything a sweep should reach. A run that hits it measures the ceiling instead of the system |
| Go API trigger | prometheus · `sum(rate(container_cpu_usage_seconds_total{namespace="rag-api",...}[2m]))` · threshold `0.2` · `metricType: AverageValue` | `api-scaler` ScaledObject                           | decides how many replicas appear at a given arrival rate |
| Go API requests / limits | `cpu 250m / 500m` · `mem 256Mi / 512Mi`                                                                | `deploy/k8s/apps/api/deployment.yaml`               | per-replica capacity, and the denominator every CPU reading is taken against |
| TEI `minReplicaCount` | 2                                                                                                       | `tei-embeddings-scaler` ScaledObject                | the other always-on half of the serving Floor line |
| TEI `maxReplicaCount` | 30                                                                                                      | `tei-embeddings-scaler` ScaledObject                | as above |
| TEI trigger | prometheus · `sum(rate(container_cpu_usage_seconds_total{...}[2m]))`, `metricType: AverageValue` · threshold `1.5` · `pollingInterval: 15` | `tei-embeddings-scaler` ScaledObject                | TEI is shared: the indexer drives it during ingestion and the API during queries, so this row moves figures in both executions. `sum()`, not `avg()` — `avg()` pinned desiredReplicas at ~1 regardless of load (2026-09-01 fix) |
| TEI requests / limits | `cpu 3 / 4` · `mem 768Mi / 1Gi`                                                                         | `deploy/k8s/platform/tei-embeddings/deployment.yaml`| per-replica capacity. Raised from `2/4` cpu request 2026-09-01 — node-level overcommit at the old 2-core request (measured 171% of node allocatable in limits under load) |
| Qdrant nodes | 2 × `r7g.large` On-Demand, `desired_size` 2 (`max_size` 3)                                              | `eks_database_nodes` (`terraform/modules/01-rag-core/eks.tf`) | the database does not autoscale on either path, so this is the one ceiling a replica change cannot relieve. Memory-optimized and not burstable: a `t` class would make each point's capacity depend on how long the cluster idled before it |
| Qdrant sharding | `shard_number` 1 (default, not set) · `replication_factor` 2                                            | `apps/indexer/src/haystack_pipeline.py` (`QdrantDocumentStore(...)`) | decides whether the second node holds data or is paid for and idle — one shard, replicated, so both nodes hold the full collection |
| Qdrant collection config | INT8 SQ on (quantile 0.99, `always_ram`) · 384 dims · sparse on · `hnsw_m`/`hnsw_ef` not set — Qdrant client default | `apps/indexer/src/haystack_pipeline.py` (`QdrantDocumentStore(...)`), not Helm values | changes write cost, read latency and RAM together |
| Bedrock stub delay | 2000 ms                                                                                                 | `apps/api/core/domain.go` mock_delay_ms query param | every latency figure in this report is read against it |
| App pod label | `app=⟨chunker · indexer · api · tei-embeddings⟩`                                                        | every workload manifest                             | the grouping key for pod-level cost; generated Job names are not one |
| Job history retention | `successfulJobsHistoryLimit` 3 · `failedJobsHistoryLimit` 3 · `ttlSecondsAfterFinished` not set          | `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml`  | worker concurrency and termination reasons are read from Job and Pod objects, and garbage collection removes those series mid-window |
| Image digests | chunker `sha-404a267` · indexer `sha-32365dc` · api `sha-bafdc1f` · tei `cpu-1.6` (tag only, no digest pin) · qdrant `v1.18.2` — tags, not `sha256:` manifest digests; `./data/identity-2026-09-05.txt` | | the one thing that must not move while the config commit does · the Qdrant digest is an `arm64` manifest and the rest are `x86_64` |

### Cost basis → report §4

- **Source of record** — CUR 2.0, hourly, resource IDs and split cost allocation on, at `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag`. Every measured cost figure in this report is a sum over its rows
- **Cost column** — `line_item_unblended_cost`, used everywhere in this report. Differs from `line_item_amortized_cost` for the same node under a Savings Plan; not chosen here since none is active on this account
- **Line-item types summed** — `Usage`, `DiscountedUsage`, `SavingsPlanCoveredUsage`. Tax, credits, refunds and monthly fees are excluded: they land in an arbitrary hour and corrupt a window
- **Region and currency** — `eu-central-1` (`terraform/variables.tf`, not overridden in `terraform.tfvars`) · USD
- **Rate card** — `./data/price-2026-09-09.json`, carried only for what no run buys: Fargate vCPU-hour and GB-hour, and Bedrock per 1K input and output tokens (real AWS Price List API reads, not list-price recall). The Bedrock rates are consumed by `02-inference` (`E18`) and no figure in this execution uses them. Every other rate is in the CUR rows themselves, already dated
- **Spot** — priced at what was actually charged in each run hour. No historical average is frozen and none is needed
- **Reader** — `./scripts/aws-cur-report-export.py`, one window per invocation

### Envelope → report §2

- **Platform** — `eu-central-1` · EKS `1.36` (terraform default, not live-verified — cluster is gone) · Karpenter `1.13.0` · KEDA `2.14.2` · mixed architecture: core-on-demand nodes `x86_64`, every other pool like db, api and jobs `arm64`. Re-measure on any node-type or architecture change
- **Topology** — two Qdrant replicas on dedicated `r7g.large` nodes, one shard replicated across both (not sharded — both hold the full collection), 84,018 points once loaded (`01-ingestion`'s 100-file sample, confirmed identical at every point from `n50-test` through `n10` — `R21`). One cluster, no co-tenant load. Re-measure on a different replica count or shard layout
- **Autoscaling** — both serving deployments scale from 2 replicas under the triggers frozen above. Every figure in both executions is conditional on those triggers, not on a replica count. Re-measure on any trigger or threshold change
- **Egress** — S3 leaves through a gateway endpoint. Bedrock leaves through its two interface endpoints. SQS and every other AWS API call cross NAT and are billed per gigabyte
- **Generation** — stubbed at the frozen delay. No run in this report calls Bedrock
- **Floor state** — captured against an empty collection and an idle ingestion pool. It prices the system before either execution has put anything in it
- **Commercial** — the cost column and rate card above, as of 2026-09-09 (rate card date; every CUR row carries its own date already). Re-measure on any rate change
- **Outside** — multi-region, GPU inference, managed vector SaaS

### Floor → report §4.1

Captured over the idle window. Every `$/month` is D4.

Compute is priced by node pool, not by workload. Everything scheduled onto `core-on-demand` —
ArgoCD, CoreDNS, Cilium agents, Prometheus, Loki, Grafana — is already inside that one line, and
listing any of them again would count it twice. Persistent volumes are separate line items and
appear on their own.

| Line | Block | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| EKS control plane | A | $73.00 ᴿ | fixed |
| `core-on-demand` node group — compute + root EBS | A | $144.02 ᴿ | fixed |
| `core-on-demand` — regional data transfer | A | rate $0.01/GB ᴿ (flat, confirmed on every sampled row) — the capture hour's own GB figure is not usable, same reasoning as NAT's per-GB line below (see Floor notes) | variable |
| Monitoring persistent volumes — Prometheus, Loki gp3 | A | $1.90 ᴰ | fixed |
| Karpenter on Fargate | A | $24.91 ᴿ ⚠ provisional | fixed |
| NAT gateway — hourly | A | $37.96 ᴿ | fixed |
| NAT gateway — per GB at idle | A | rate $0.052/GB — the capture hour's own GB figure is not usable (see Floor notes) | variable |
| `database-on-demand` node group — 2 × `r7g.large`, compute + root EBS | B | $192.50 ᴿ | fixed |
| `database-on-demand` — regional data transfer | B | rate $0.01/GB ᴿ — same flat rate as `core-on-demand`'s above, same reasoning, not extrapolated | variable |
| Qdrant PVC data volumes — `qdrant-storage-qdrant-{0,1}`, 50Gi × 2, current generation only | B | $9.65 ᴿ | fixed |
| Qdrant PVC data volumes — 2 older-generation duplicates, likely orphaned (see Floor notes) | B | $9.65 ᴿ, not folded into any total below — flagged as probable waste, not a confirmed cost of running the system | fixed, unconfirmed necessity |
| ~~Standalone EBS volume `simple-rag-qdrant-data` (150GB)~~ — removed from Terraform 2026-09-09 | — | $14.47 found, then excluded — a config bug, not a cost of running the system (see Floor notes) | n/a |
| Qdrant snapshot storage | B | ~$0 this hour (bucket empty — confirmed, 0 request-cost rows) ᴿ, still no non-zero measurement of the rate itself | variable |
| Interface VPC endpoints — `bedrock`, `bedrock-runtime` | B | $52.56 ᴿ | fixed |
| `apps-serving` nodes at minimum replicas — 2 API, 2 TEI, compute + root EBS | B | $152.51 ᴿ ⚠ provisional | fixed |
| `apps-serving` — regional data transfer | B | rate $0.01/GB ᴿ — same flat rate found on every other pool's transfer line, same reasoning, not extrapolated (see Floor notes) | variable |
| Load balancer behind the Gateway | B — routes only to this feature's API, leaves with it (`report.md`'s own Block B definition) | $19.71 ᴿ base + variable LCU usage (LCU still unmeasured) | fixed base / variable usage |
| S3 — empty bucket | B | ~$0 ᴿ (confirmed against both buckets this hour) | variable |
| SQS — idle scaler polling | B | ~$0 ᴿ (confirmed — every queue's request-cost row was $0 this hour) | variable |

Superseded 2026-09-05 by a real `M1` read (`ᴿ` rows above). List-price math kept only for what
`M1` still can't reach: Monitoring PVs ($1.90 ᴰ — `gp3` volumes untagged, can't isolate from
`core-on-demand`'s own) and the Qdrant snapshot rate (no measurement, bucket was empty).

**Bootstrap traffic vs. idle traffic** — 0 EC2 instances existed the hour before capture; 11 join
and pull images during the captured hour (NAT-Bytes alone is 74% of its network spend). A
settled hour, same cluster, two hours after the day's campaign ended (20:00–21:00, 1 instance
left): NAT is `$0/h`, a >50x drop. One-time bootstrap network cost ≈ **$0.62** (this hour only,
doesn't recur). Steady idle network cost ≈ **$0/hour**. Every usage-based line in the table
above (NAT, regional transfer) is reported as a $/GB rate, not extrapolated, for this reason.

**Compute lines were understated, fixed 2026-09-09.** `core-on-demand`/`database-on-demand`'s
node `usage_amount` isn't 1.0 this hour (nodes joined mid-bucket, per above) — `0.6475` and
`0.227`/`0.646` node-hours. The old rows divided cost by the 1-hour bucket instead of by actual
existence; correct is `cost ÷ amount`. `database-on-demand`: $0.12921/node-hour — matches the
on-demand list rate exactly, closing the earlier ⚠ reconciliation gap. `core-on-demand`:
$0.09600/node-hour. Corrected: core $144.02/month (was $94.62), database $192.50/month (was
$86.23) — database is now the pricier pool, by $48.48/month.

`apps-serving` and Karpenter's Fargate pods show the same signature but aren't cleanly fixable:
`apps-serving` ran 4 different Spot instance types this hour (consolidation churn, no single
steady-state rate to recover); Karpenter's pods' unit rate matches the AWS Price List API exactly,
but the monthly figure needs their CPU/memory request, not observed this hour. Both marked
`⚠ provisional` — likely understated, not corrected. `apps-serving`'s rate is what both other
executions subtract from every run window; `02-inference`'s §3 Matrix inherits the same
`⚠ provisional` status.

`apps-serving`'s per-workload split (M12): `tei-embeddings` $0.07447 vs. `api` $0.00651 this
hour — TEI ~11x API's share, consistent with its larger request. Partial figure: excludes the
pool's unused/headroom capacity ($0.30541, fleet-wide) → `./data/m12-eks-split-2026-09-04.json`.

Monitoring PVs likely has the same duplicate-PVC problem as Qdrant below: 4 ~10GB volumes exist
tagged for monitoring, not the assumed 2 — two generations each for Loki-0 and Prometheus-0. Not
resolved into a ᴿ figure (needs a live-attachment check the cluster no longer allows).

The old "Qdrant gp3 volumes" row was mislabeled — it priced `database-on-demand`'s own root
volumes (2×20GB), not Qdrant's data. Qdrant's real PVC (`persistence.size: 50Gi`,
`qdrant-values.yaml:36`) is 4 volumes, not 2 — two generations per pod, consistent with a
StatefulSet recreation that left the old generation uncleaned (plausibly `01-ingestion`'s
`pre-n50-manual-wipe`). Current generation ($9.65/month) is in Block B; the older pair is
flagged as probable orphaned waste, not summed into any total.

A separate 150GB standalone EBS volume (`aws_ebs_volume.qdrant`) was never Qdrant's real storage
and had no `aws_volume_attachment` anywhere in the repo — removed from Terraform 2026-09-09
(resource plus the 3 chained `qdrant_ebs_volume_id` outputs; `terraform validate` clean).
Excluded from Block A: real spend while the bug existed, but a config bug, not a floor cost.

`database-on-demand`'s Terraform module tags nodes `tier = "database"`, not
`"database-on-demand"` (`nodes.tf:72` vs. `:112`) — name/tag drift, harmless here, a trap for a
future filter on the wrong string.

- **A · Shared** — $281.79 known-fixed + 2 unmeasured variable lines (NAT per-GB, `core-on-demand` transfer)
- **B · Dedicated** — $426.93 known-fixed (includes the $19.71 LB — resolved to B, see Configuration freeze table), excludes the second Qdrant PVC pair → report §1 BLUF
- **C · Total** — $708.72/month known-fixed (A + B); carries 2 `⚠ provisional` lines (`apps-serving`, Karpenter Fargate)
- **Serving pool idle rate** — $0.20892/hour ᴿ ⚠ provisional ($152.51/month, `apps-serving` row above)
- **Untaggable lines allocated by hand** — R5, $0.21163 of $0.21163, all Block A → `./data/untaggable-2026-09-04.txt`
- **Reference value** — the unqualified idle claim published in article 1. No always-on floor is carried
- **Raw data** — `./data/idle-2026-09-04.csv` (728 CUR rows for the 13:00–14:00Z hour)

### Retro

- **Expectation** — partly held. `database-on-demand` (Qdrant's nodes) is the largest B line at 45.1% ($192.50 of $426.93) — direction right, but not the predicted majority. Rank order inverted below it: `apps-serving` is second at 35.7% ($152.51), not third; Bedrock endpoints are third at 12.3% ($52.56), not second. Qdrant's own PVC data is 2.3% ($9.65) — negligible next to the compute line hosting it
- **Attribution coverage** — `M2` fails its own 5% gate at capture (14.3%), kept anyway per K1 (see Metrics table). R5 (2026-09-09) accounts for the whole gap in dollar terms: 8 non-zero untagged lines, $0.21163, all platform overhead landing in Block A — mostly a resolution of *why* M2 is high (structurally-untaggable AWS-managed lines: EKS control plane, Karpenter's Fargate pod, public IPv4, KMS), not evidence of a real tagging gap in this project's own resources, apart from two lines (EKS control-plane hours, LB usage) that are tagged but don't carry it through to CUR — real, narrow, worth fixing at the source
- **Cost against estimate** — no capture-specific budget was set for this execution; not applicable
- **Month-close revision** — not yet — September closes in October, K3's second read is still open
- **Not observed** — M3 (node inventory, cluster torn down before the gap was noticed); Qdrant hnsw config (assumed at client default, never read live); EKS control-plane version (terraform default, never read live); `apps-serving` and Karpenter Fargate compute rates (⚠ provisional, partial-hour billing bug found but not correctable from this hour); Monitoring PVs' and the second Qdrant PVC pair's live-attachment status (cluster gone) → report Coverage
