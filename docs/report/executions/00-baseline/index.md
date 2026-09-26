# 00 · Baseline

- **Purpose** — system at rest: frozen configuration, cost attribution, price basis, floor
- **Produces** — frozen config · cost basis · metric register · floor baseline
- **Expected** — recorded 2026-08-31, before capture (`git log -S`, commit `bafdc1f`): Block B is dominated by the two Qdrant nodes and their gp3 volumes, at more than half of B; the Bedrock endpoints are second and the serving pool at minimum replicas third
- **Revision** — v1.0 (supersedes none)
- **Capture window** — 2026-09-04 18:00 → 19:00 UTC, the resting hour: `n25` drained at ~17:50, teardown began at 19:00, 6 nodes ran the full hour and `apps-compute` was at zero. The original capture hour 13:00 → 14:00 was the node-bootstrap hour (0 EC2 instances the hour before, 11 joined during it) and no longer feeds the Floor
- **Frozen at** — `cfa0ab79` · by maksimillian1. This is the commit that was live during the capture window (2026-09-03T16:19:08Z, ~20h40m before the window opened) and the last one before `15d43d5b`. `15d43d5b` (2026-09-04T13:47:53Z) lands inside the window, but it raises `maxReplicaCount` for the upcoming `n125` point and is not the state the idle hour was captured against
- **Capture notes** — anomaly: the idle-window criterion doesn't fit how this project operates (Preflight revision, 2026-09-05), because no cluster here sits idle for a full day. The one clean hour that existed was captured instead, read from CUR after the cluster had been torn down, once `01-ingestion`'s CUR pull exposed the gap. M2 reads 25.6<!--FD126-->% over that hour, and is a reading rather than a gate (Metrics table); M3 wasn't captured (cluster gone). The Floor is CUR inventory × unit rate from one resting hour, not the diurnal and monthly picture the original design wanted

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
- [x] Kubernetes label import enabled for `app`. Like the split-cost preference, this is console-only and not part of `bcm-data-exports`' `TableConfigurations` (`get-table` lists only `TIME_GRANULARITY`, `INCLUDE_RESOURCES`, `INCLUDE_SPLIT_COST_ALLOCATION_DATA`, `INCLUDE_MANUAL_DISCOUNT_COMPATIBILITY`), so the console is where it is set.
- [x] Data Exports → CUR 2.0 export created via `aws bcm-data-exports create-export`: `HOURLY`, `INCLUDE_RESOURCES=TRUE`, `INCLUDE_SPLIT_COST_ALLOCATION_DATA=TRUE`, Parquet/Parquet, `OVERWRITE_REPORT`, into `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag`. `ExportStatus: HEALTHY` (2026-09-01). First delivery pending; CUR does not backfill.

**Confirmed before the window opens**

- [x] First export file present in the bucket. Confirmed after the fact rather than by a preflight check: the first `M1` pull (2026-09-05) read real rows from this export, and both `01-ingestion` and `02-inference` later pulled from the same path.
- [x] `feature` and `tier` non-empty on EC2, EBS, SQS, S3 and endpoint rows. Confirmed after the fact through `M1`: `tier` splits EC2 cleanly into core / database / serving (Floor table) and the two Bedrock endpoints price as their own tagged line. Qdrant's gp3 volumes do **not**: R5 found them in the untagged set, identified by size, so the Floor's Qdrant PVC row rests on the volume inventory rather than on a tag, and SQS and S3 match their own zero-cost rows. `feature`'s fill rate is `M2`'s complement (74.4<!--FD128-->% of the resting hour's dollars), an aggregate over the hour rather than the per-product-code breakdown this line asks for.
- [x] `split_line_item_*` columns present; chunker, indexer, api and tei appear as separate rows under a smoke load. Confirmed 2026-09-09 by reading the parquet directly, in hindsight rather than as a preflight step. All 11 `split_line_item_*` columns are present in the schema and populated for `AmazonEKS` rows; per-pod rows exist and are tagged down to `resource_tags['aws_eks_workload_name']`/`['aws_eks_namespace']`/`['aws_eks_node']`. Confirmed present for `api`, `tei-embeddings` and `qdrant` in this execution's own idle hour (`chunker`/`indexer` are at ~$0 here since neither runs at idle) → `./data/m12-eks-split-2026-09-04.json`. Caveat: split-cost rows lag ordinary CUR rows by several days (ordinary rows reach 2026-09-09, non-zero split rows stop at 2026-09-05T16:00Z). That doesn't affect this hour (2026-09-04), but it matters for any near-real-time re-run.
- [x] Split rows checked against their parent instance rows for double counting. Not checked row by row. Double counting is ruled out by construction: `AmazonEKS`'s split rows re-express the same `AmazonEC2` instance-hour cost, apportioned across the pods that ran on the instance by resource-request ratio, plus one `unused` remainder row per instance. They are not a second, separately billed charge. Summing a node's split rows (attributed + unused) reconstructs that node's own instance cost rather than adding to it.
- [x] Lines that cannot carry a tag enumerated → `./data/untaggable-2026-09-04.txt`, each mapped to the Floor row that already prices it (R5). Pulled 2026-09-09, rewritten as a mapping and re-pulled for the resting hour 18:00–19:00Z on 2026-09-26: 11 non-zero product/usage-type combos, $0.3758642<!--FM57-->, every one of them resolving to a row that already prices it. There is no hand allocation to a block any more, because there was nothing to allocate — this is the same money the Floor already prices by resource, and adding it to a block would double-count it. The block of each line is therefore its Floor row's block. That corrects the earlier reading of this file: the four untagged 50 GB gp3 rows are Qdrant PVCs, so **some of the untagged money is Block B**, and the leftover volumes among them are in the errors table rather than in any block. Two lines (EKS control-plane hours, the LB) are tagged resources whose tag doesn't reach their flat hourly CUR line — a narrow tagging-visibility gap worth fixing at the source.
- [x] M2 measured. **Re-pulled 2026-09-26 for the resting hour 18:00–19:00Z, the hour the Floor is built on: 25.6<!--FD126-->%** — $0.3758642<!--FM57--> of the $1.465973<!--FM56--> billed in it (`./data/idle-2026-09-04T1800.csv`). The first reading, 14.3% over the 13:00–14:00Z bootstrap hour, is superseded: it described an hour no figure rests on. Reworded at the same time: it was written as a validity gate that had to read under 5%, and it is not one. Everything in this deployment that can carry a `feature` tag carries it; what arrives without one is AWS-managed flat charges, each already priced as its own row by resource (R5). **The share rose for one reason and it is not tagging**: the largest untagged line at rest is the CloudWatch vended-log charge, $0.1382863<!--FD125-->, which read $0.00000 in the bootstrap hour — the EKS control-plane logging defect (FM8, FD34), outside every Floor figure. Without it the share is 17.9<!--FD127-->%.

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
| M1 | idle spend per line over the idle window | CUR 2.0 parquet at `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag` · the frozen cost column (`line_item_unblended_cost`) where `line_item_line_item_type` is a usage type and `line_item_usage_start_date` falls inside the window · grouped by `line_item_product_code`, `resource_tags['user_tier']`/`['user_karpenter_sh_nodepool']`, `line_item_resource_id` · read directly with `pyarrow` for the 2026-09-05 pull; `./scripts/aws-cur-report-export.py` reproduces it as of 2026-09-26, once a null-handling bug in its split-child guard was fixed — `pc.or_` propagates null, so every ordinary row was dropped and the tool returned an empty result on any export where a parent id is null | confirmed 2026-09-05 over 13:00–14:00Z; **re-read 2026-09-26 over the Floor's own resting hour 18:00–19:00Z** (`./data/idle-2026-09-04T1800.csv`), which cross-checks FM1, FM2's CUR input, FM3, FM8, FR7, FR12, FR18 and FD6's inventory. A cross-check, not a second derivation: the monthly figures stay inventory × published rate × 730 | every Floor line is a group of this. The `tier` tag is what splits EC2 into core, database and serving lines; without it EC2 arrives as one number. Endpoint hours are billed per ENI per availability zone and arrive as one row per ENI |
| M2 | share of the resting hour's whole bill arriving with no `feature` tag | same source, tag absent; **denominator is every ordinary row in the hour**, $1.465973<!--FM56-->, not the taggable subset; split-cost children excluded as in the Floor | re-pulled 2026-09-26 for the Floor's own hour: **25.6<!--FD126-->%** ($0.3758642<!--FM57--> / $1.465973<!--FM56-->, hour 18:00–19:00Z). First read 14.3% over the 13:00 bootstrap hour, superseded | a reading, not a gate, and not a report figure. It was written as a < 5% validity gate; removed 2026-09-26, because nothing here that can carry a `feature` tag is missing one — the remainder is AWS-managed flat charges (EKS control-plane hours, Karpenter's Fargate pod, per-ENI public IPv4, KMS keys, the LB), each priced as its own row by resource, which is what R5 maps. A threshold would be measuring AWS's tagging, not ours. The one row that is ours is the untagged gp3 volumes, and → K1 names its mechanism: the CSI driver tags from storage class parameters that are immutable after creation, so a PVC provisioned once stays untagged. The rise from 14.3% is a defect entering the numerator, not a tagging regression: the CloudWatch vended-log line is $0.1382863<!--FD125--> of it (FD34) and reads $0 in the bootstrap hour; net of it the share is 17.9<!--FD127-->% |
| M3 | node inventory during the idle window | `kube_node_labels` · selector on `label_karpenter_sh_nodepool` | not done: the cluster was already torn down when the gap was noticed (2026-09-05), so nothing was left to query | proof of idleness: `apps-compute` at zero for the whole window, `apps-serving` steady. Node labels are not exported by kube-state-metrics unless `--metric-labels-allowlist` includes them, and without it the query returns nothing on a healthy cluster. Approximated instead from CUR's `resource_tags['user_karpenter_sh_nodepool']` tag on the EC2 rows (Floor), a different source from the one M3 names, supporting the same claim |
| D4 | monthly floor per line | resources alive the full resting hour 2026-09-04 18:00 (CUR inventory) × unit rate × 730; EBS as size × $/GB-month; variable lines as rest-hour usage × rate × 730 | active | 730 is the AWS monthly-hour convention; the extrapolation assumes the resting hour is typical → K3 |
| R5 | which Floor row already prices each untagged CUR line, and therefore which block it is in | hand-recorded from `./data/untaggable-2026-09-04.txt` · maksimillian1 | active; rewritten as a mapping and re-pulled for the resting hour 2026-09-26, $0.3758642<!--FM57--> over 11 non-zero combos | not an allocation: untagged money is not separate money, it is Floor money seen through the tag column, so it is mapped rather than assigned and nothing sums into a total. Was an A-or-B judgement until 2026-09-26, which is how the file came to say all of it was A. Two lines needed real decisions and both are recorded where the Floor prices them: the Gateway's NLB (A, `nlb` FD19) and the untagged 50 GB gp3 volumes (Qdrant PVCs, B, FD14, with the leftovers in the errors table). The second is → K1's consequence arriving in full: FD14 rests on the volume inventory, not on a tag |

---

## 2 · Results

### Configuration freeze

System configuration params under test.

| Parameter | Value                                                                                                   | Set in                                              | Why frozen |
| :--- |:--------------------------------------------------------------------------------------------------------|:----------------------------------------------------| :--- |
| `apps-compute` instance type | `c7g` family only · sizes `xlarge`/`2xlarge`/`4xlarge` · spot only                                      | Karpenter NodePool (`deploy/k8s/platform/karpenter-resources/templates/nodepool.yaml`) | one type keeps the ingestion pool priced at one rate |
| `apps-compute` `consolidateAfter` | 5 m, with `consolidationPolicy: WhenEmpty` | Karpenter NodePool | the teardown tail is billed and sits inside every run window. Corrected 2026-09-26: this row used to read `30 s`, the plan value from `bafdc1f` (2026-08-31). `cfa0ab7` raised both pools to `5m` on 2026-09-03, after a scheduling deadlock (postmortem 2026-09-02) — a day before the resting hour and before every run in this report, so `30 s` never applied to a measured figure |
| `apps-serving` instance types | `instance-category In [c]`, `arch In [amd64,arm64]`, `instance-size In [xlarge,2xlarge,4xlarge]`, spot+on-demand (`deploy/k8s/platform/karpenter-resources/templates/nodepool.yaml`, 2026-09-03) | Karpenter NodePool                                  | narrowed from `[c,m,r]` to `c` only; size floor raised from unset to `xlarge` because TEI no longer fits a smaller node at its current request. Both architectures were open during the campaign, deliberately: `tei-embeddings` is amd64-only (`nodeSelector`, no arm64 image manifest) while `api` is multi-arch and took arm64 twice — one c7g.4xlarge at `n75`, one c8g.xlarge at `n125`. That leaves up to 6 concrete types (2 arches × 3 sizes) instead of one price, much narrower than the old fully open `[c,m,r]` range but still not one. **The pool was narrowed to `arch In [amd64]` on 2026-09-26**, after the campaign, so one tier could not sit on hardware the other cannot use; the frozen value above is what every figure in this report was measured on |
| `apps-serving` `consolidateAfter` | 5 m, with `consolidationPolicy: WhenEmptyOrUnderutilized` | Karpenter NodePool | decides how much of a scale-out tail each query window carries. Corrected 2026-09-26 with the row above, from the plan value `1 m` |
| chunker requests / limits | `cpu 100m / 500m` · `mem 512Mi / 1Gi`                                                                   | `deploy/k8s/apps/chunker/scaledjob.yaml`            | sets workers per node, and split cost allocation divides a node by requests. Resized 2026-09-01 from measured p90/max CPU and memory over `ingestion-n50-test` (100-file sample). The limit keeps ~2.3x margin over the observed 433Mi max; the corpus has untested files up to 124 MB |
| indexer requests / limits | `cpu 500m / 2` · `mem 2Gi / 4Gi`                                                                        | `deploy/k8s/apps/indexer/scaledjob.yaml`            | as above; the memory limit is what every termination reading is judged against |
| Go API `minReplicaCount` | 2                                                                                                       | `api-scaler` ScaledObject                           | the always-on half of the serving Floor line |
| Go API `maxReplicaCount` | 10                                                                                                      | `api-scaler` ScaledObject                           | set above anything a sweep should reach. A run that hits it measures the ceiling instead of the system |
| Go API trigger | prometheus · `sum(rate(container_cpu_usage_seconds_total{namespace="rag-api",...}[2m]))` · threshold `0.2` · `metricType: AverageValue` | `api-scaler` ScaledObject                           | decides how many replicas appear at a given arrival rate |
| Go API requests / limits | `cpu 250m / 500m` · `mem 256Mi / 512Mi`                                                                | `deploy/k8s/apps/api/deployment.yaml`               | per-replica capacity, and the denominator every CPU reading is taken against |
| TEI `minReplicaCount` | 2                                                                                                       | `tei-embeddings-scaler` ScaledObject                | the other always-on half of the serving Floor line |
| TEI `maxReplicaCount` | 30                                                                                                      | `tei-embeddings-scaler` ScaledObject                | as above |
| TEI trigger | prometheus · `sum(rate(container_cpu_usage_seconds_total{...}[2m]))`, `metricType: AverageValue` · threshold `1.5` · `pollingInterval: 15` | `tei-embeddings-scaler` ScaledObject                | TEI is shared: the indexer drives it during ingestion and the API during queries, so this row moves figures in both executions. `sum()` rather than `avg()`, because `avg()` pinned desiredReplicas at ~1 regardless of load (2026-09-01 fix) |
| TEI requests / limits | `cpu 3 / 4` · `mem 768Mi / 1Gi` (the code carries this value; `1ef1f0a` raised it to `cpu 6 / 8` for `inference-r1000` alone and it was put back on 2026-09-26) | `deploy/k8s/platform/tei-embeddings/deployment.yaml`| per-replica capacity. CPU request raised from `2/4` on 2026-09-01 after node-level overcommit at the old 2-core request (limits measured at 171% of node allocatable under load). Every figure in this report rests on `3 / 4` except `02-inference`'s `r1000` point |
| Qdrant nodes | 2 × `r7g.large` On-Demand, `desired_size` 2 (`max_size` 3)                                              | `eks_database_nodes` (`terraform/modules/01-rag-core/eks.tf`) | the database does not autoscale on either path, so this is the one ceiling a replica change cannot relieve. Memory-optimized and not burstable: a `t` class would make each point's capacity depend on how long the cluster idled before it |
| Qdrant sharding | `shard_number` 1 (default, not set) · `replication_factor` 2                                            | `apps/indexer/src/haystack_pipeline.py` (`QdrantDocumentStore(...)`) | decides whether the second node holds data or is paid for and idle. One shard, replicated, so both nodes hold the full collection |
| Qdrant collection config | INT8 SQ on (quantile 0.99, `always_ram`) · 384 dims · sparse on · `hnsw_m`/`hnsw_ef` not set (Qdrant client default) | `apps/indexer/src/haystack_pipeline.py` (`QdrantDocumentStore(...)`), not Helm values | changes write cost, read latency and RAM together |
| Bedrock stub delay | 2000 ms                                                                                                 | `apps/api/core/domain.go` mock_delay_ms query param | every latency figure in this report is read against it |
| App pod label | `app=⟨chunker · indexer · api · tei-embeddings⟩`                                                        | every workload manifest                             | the grouping key for pod-level cost; generated Job names are not one |
| Job history retention | `successfulJobsHistoryLimit` 3 · `failedJobsHistoryLimit` 3 · `ttlSecondsAfterFinished` not set          | `deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml`  | worker concurrency and termination reasons are read from Job and Pod objects, and garbage collection removes those series mid-window |
| Image digests | chunker `sha-404a267` · indexer `sha-32365dc` · api `sha-bafdc1f` · tei `cpu-1.6` (tag only, no digest pin) · qdrant `v1.18.2`. These are tags, not `sha256:` manifest digests; `./data/identity-2026-09-05.txt` | | the one thing that must not move while the config commit does. **What each ran on** (corrected 2026-09-26; the row used to say "the Qdrant digest is an `arm64` manifest and the rest are `x86_64`", which confused the image's manifest with the node's architecture and was wrong on both counts): qdrant on `database`, r7g.large, **arm64** · chunker and indexer on `apps-compute`, **arm64 only** — 91 node-instances across the campaign, every one a `c7g`, as that NodePool admits no other family · api and tei-embeddings on `apps-serving`, **amd64 at rest and in all but two**: c7i-flex.2xlarge for the resting hour, c5/c5a/c5d/c5ad/c6a/c6i/c7i-flex through the campaign, plus one c8g.xlarge (`n125`) and one c7g.4xlarge (`n75`) · the platform stack on `core`, t3.large, amd64 · Karpenter on Fargate, amd64. Those two arm64 nodes carried `api`, not `tei-embeddings`, and the manifests settle it rather than the billing: `tei-embeddings/deployment.yaml` pins `kubernetes.io/arch: amd64` because its image has no arm64 manifest, while `api` constrains only `karpenter.sh/nodepool` and the NodePool admits `arch In [amd64,arm64]` on purpose. So the embedding tier is amd64 by construction, and the API tier was not until the pool was narrowed to `arch In [amd64]` on 2026-09-26 — after every measurement here. The manifest architectures themselves were never captured: `identity-2026-09-05.txt` records tags, not `sha256:` digests |

### Cost basis → report §4

- **Source of record** — CUR 2.0, hourly, resource IDs and split cost allocation on, at `s3://simple-rag-cur-reports-883f615c/cur2/simple-rag`
- **Method** — `methodology.md` §9, "Cost calculation approach (AWS)". Nothing here departs from it
- **Cost column** — `line_item_unblended_cost` (§9). `line_item_amortized_cost` differs for the same node under a Savings Plan; none is active on this account
- **Region and currency** — `eu-central-1` (`terraform/variables.tf`, not overridden in `terraform.tfvars`) · USD
- **Rate card** — `./data/price-2026-09-09.json` plus every `R` figure in `figures.yaml`. Some are read off CUR rows, some from the AWS Price List API — the PrivateLink per-GB rate was pulled 2026-09-22, later than the rest. Fargate and Bedrock are carried because no run buys them. **A monthly fee is the one place where an hourly CUR row and the rate card disagree, and the card wins** (§9): `eu-central-1-KMS-Keys` bills $0.0013889/h because AWS prorated $1.00 across September's actual 720 hours, so projecting the hour on the 730-hour convention would read $1.0139. FD8 is $1.00 from FR19. Verified against the resting hour 2026-09-26; every other hourly line reads the same either way
- **Spot, which hour** — the Floor rests on 09-04's resting hour, `02-inference` nets its campaign against 09-05's, and the two differ by half
- **Reader** — the CUR parquet, read directly with `pyarrow` (M1). `./scripts/aws-cur-report-export.py` does the same job for a named window and was proved against this hour on 2026-09-26, after a null-handling fix to its split-child guard — `pc.or_` propagates null, so rows with no parent id were dropped and the tool returned an empty result; with `or_kleene` it reproduces both captured hours to the cent. Its split reconciliation was repointed at the same time: it compared pod-attributed cost against the whole window bill, which can never agree, and now checks `split + unused` against the compute rows of the instances the split came from — +0.0% on both hours. The prefix it needs is `figures.yaml meta.cur`

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
| EKS control plane | A | 1 cluster | $0.10<!--FR7-->/h | 73.00<!--FD1--> |
| `core-on-demand` nodes | A | 2 × t3.large On-Demand, amd64 | $0.0960<!--FR8-->/h | 140.16<!--FD2--> |
| `core-on-demand` root EBS | A | 2 × 20 GB gp3 | $0.0952<!--FR2-->/GB-mo | 3.81<!--FD3--> |
| Karpenter on Fargate | A | 2 pods × 0.5 vCPU / 1 GB (requests 300m / 512Mi, `karpenter.tf`) | $0.04656<!--FR5-->/vCPU-h + $0.00511<!--FR6-->/GB-h | 41.45<!--FD4--> |
| NAT gateway | A | 1 (single NAT) | $0.052<!--FR12-->/h | 37.96<!--FD5--> |
| Public IPv4 | A | 4 (NAT + internet-facing NLB in 3 AZs) | $0.005<!--FR13-->/h | 14.60<!--FD6--> |
| Monitoring PVs | A | 2 × 10 GB gp3 (Prometheus, Loki; current generation) | $0.0952<!--FR2-->/GB-mo | 1.90<!--FD7--> |
| KMS key | A | 1 | $1.00<!--FR19-->/key-month | 1.00<!--FD8--> |
| Load balancer (NLB behind the Gateway) | A | 1; LCU $0 at rest. `rag-platform`'s Gateway, `allowedRoutes: from: All`, already parents `/` → api and `/monitor` → Grafana, so it survives the feature | $0.027<!--FR18-->/h | 19.71<!--FD19--> |
| **A fixed** | | | | **333.59<!--FD21-->** |
| `core-on-demand` cross-AZ, source unknown | A | 0.877<!--FM2--> GiB/h (9.893 core − 9.016 ArgoCD) | $0.01<!--FR3-->/GB | 6.40<!--FD9--> |
| NAT processing | A | 0.053<!--FM3--> GiB/h | $0.052<!--FR4-->/GB | 2.01<!--FD10--> |
| Other cross-AZ (NAT, Fargate, EKS ENIs) | A | 0.194<!--FM4--> GiB/h | $0.01<!--FR3-->/GB | 1.42<!--FD11--> |
| **A variable at rest** | | | | **9.83<!--FD22-->** |
| `database-on-demand` nodes | B | 2 × r7g.large On-Demand, arm64 | $0.1292<!--FR9-->/h | 188.63<!--FD12--> |
| `database-on-demand` root EBS | B | 2 × 14 GB gp3 | $0.0952<!--FR2-->/GB-mo | 2.67<!--FD13--> |
| Qdrant PVCs | B | 2 × 50 GB gp3 (`qdrant-storage-qdrant-{0,1}`; current generation) | $0.0952<!--FR2-->/GB-mo | 9.52<!--FD14--> |
| Interface VPC endpoints | B | 2 (`bedrock`, `bedrock-runtime`) × 3 AZ | $0.012<!--FR14-->/h per ENI | 52.56<!--FD15--> |
| `apps-serving` nodes | B | 2 × c7i-flex.2xlarge Spot, amd64, 1 TEI + 1 API each | $0.1912/h + $0.1882/h (Spot, as paid) | 276.96<!--FD16--> |
| `apps-serving` root EBS | B | 2 × 15 GB gp3 | $0.0952<!--FR2-->/GB-mo | 2.86<!--FD17--> |
| S3, SQS, Qdrant snapshots | B | empty buckets, idle polling | — | ~0 |
| **B fixed** | | | | **533.20<!--FD23-->** |
| Database + serving cross-AZ | B | 0.127<!--FM5--> GiB/h | $0.01<!--FR3-->/GB | 0.93<!--FD20--> |
| **B variable at rest** | | | | **0.93<!--FD24-->** |
| **C = A + B** | | fixed 866.79<!--FD27--> + variable 10.76<!--FD28--> | | **877.54<!--FD29-->** |

Left out of every total, except the `bedrock` endpoint: that one was really provisioned and really
billed, so it stays inside the as-built floor and comes out only in figure 2.

| Line | Kind | Resource | Math | $ |
| :--- | :--- | :--- | :--- | ---: |
| ArgoCD self-heal loop, cross-AZ | error | `argocd-repo-server` + `argocd-redis` (1a) → `argocd-application-controller-0` (1b), 1.35 MB/s (`./data/argocd-loop-probe-2026-09-04T1830.txt`) | 4.51 GiB/h, billed both sides = 9.02<!--FM6--> GiB/h × $0.01<!--FR3--> × 730<!--FR1--> | 65.85<!--FD32-->/month |
| ArgoCD self-heal loop, T3 CPU credits | error | core node at 42% CPU against a 30% baseline; the controller alone uses 0.6 cores | 0.248<!--FM7--> vCPU-h/h × $0.05<!--FR21--> × 730<!--FR1--> | 9.05<!--FD33-->/month |
| EKS control-plane logs | error | CloudWatch vended logs of `/aws/eks/simple-rag-cluster/cluster`: module default `audit, api, authenticator`, never chosen; switched off in Terraform (`enabled_log_types = []`) | 0.2195<!--FM8--> GB/h at rest × $0.63<!--FR20--> × 730<!--FR1--> | 100.95<!--FD34-->/month; 2.26<!--FM11--> spent (09-04, 09-05) |
| Orphaned PVCs | error | every launch left 2 × 50 GB Qdrant + 2 × 10 GB monitoring volumes (teardown never deleted PVCs); 35 volumes, 1,270 GB, all deleted by 2026-09-11 12:50Z | $74.88 billed (CUR, 08-01 → 09-11 02:00) + 9.84 h × 360 GB × $0.0952<!--FR2--> / 720 | 75.35<!--FM9--> spent; 0 now |
| Standalone EBS `simple-rag-qdrant-data` | error | 150 GB gp3 per launch, never attached; removed from Terraform 2026-09-09 | 5 volumes, 38 volume-hours billed | 0.70<!--FM10--> spent |
| `bedrock` interface endpoint | error, inside the floor | the control-plane endpoint of the two in `vpc.tf`, reachable by nothing: the API imports only `bedrockruntime`, IAM grants only `InvokeModel*`, and the Cilium policy allows only `bedrock-runtime.*.amazonaws.com` | 1 endpoint × 3 AZ × $0.012<!--FR14-->/h × 730<!--FR1--> | 26.28<!--FD47-->/month; figure 2 removes it (`docs/tech-debt.md` #12) |
| Cluster startup | one-time | NAT 8.86 GiB + cross-AZ 14.88 GiB, 09-04 12:00–14:00 | 8.86 × $0.052<!--FR4--> + 14.88 × $0.01<!--FR3--> | 0.61<!--FM12--> per launch |

- **Serving pool idle rate** — $0.3833<!--FD30-->/h ($279.82<!--FD18-->/month ÷ 730<!--FR1-->), 09-04. The pool did not rest on the same nodes every day: 09-05 rested on c5.xlarge + c6a.xlarge at $0.18754<!--FD58-->/h (`docs/report/figures.yaml`, `serving_idle_rate_0905`), so each execution nets against its own day. `01-ingestion` does this as of 2026-09-19; `02-inference`'s Matrix still carries a retired rate
- **Untaggable lines mapped to the rows that already price them** — R5, the resting hour → `./data/untaggable-2026-09-04.txt`. Mostly A, with the untagged Qdrant PVC rows in B and the leftover-volume rows in the errors table; no dollar is added to any block, because none of it is new money
- **Reference value** — the unqualified idle claim published in article 1. No always-on floor is carried
- **Raw data** — CUR parquet `BILLING_PERIOD=2026-09`, hour 2026-09-04 18:00, exported 2026-09-26 to `./data/idle-2026-09-04T1800.csv` (118 ordinary rows, $1.465973<!--FM56-->; 134 split-cost children excluded as in the Floor). `./data/idle-2026-09-04.csv` holds the original 13:00 bootstrap capture hour, which no figure rests on
- `database-on-demand` nodes are tagged `tier = "database"`, not `"database-on-demand"` (`nodes.tf:72` vs. `:112`)

### Right-sized floor (figure 2) → report §4.1

Same HA topology (2 core, 2 database, 2 serving nodes, 3 AZs, 2 Karpenter replicas). Sizes change, the 2 serving nodes are On-Demand as HA requires (`docs/tech-debt.md` #6), and the one line that is a defect rather than a size — the unreachable `bedrock` endpoint (errors table, `docs/tech-debt.md` #12) — is gone. ᴱ: priced, not run. On-Demand rates from the AWS Price List API (2026-09-11).

| Line | As built | Right-sized ᴱ | Evidence | $/month as built | $/month right-sized |
| :--- | :--- | :--- | :--- | ---: | ---: |
| Database nodes | 2 × r7g.large (2 vCPU, 16 GiB) On-Demand | 2 × c7g.large (2 vCPU, 4 GiB) On-Demand, $0.0825<!--FR10-->/h | Qdrant working set ≤ 379 MiB (M18); CPU peak 1.568 cores at r1000 keeps 2 vCPU | 188.63<!--FD12--> | 120.45<!--FE3--> |
| Serving nodes | 2 × c7i-flex.2xlarge Spot | 2 × c7i-flex.xlarge On-Demand, $0.1935<!--FR11-->/h; 1 API + 1 TEI on each | TEI + API ran on xlarge nodes the full hour 09-05 11:00; needs TEI requests 3/4 (HEAD has 6/8). The tier stays amd64 for a reason that is not sizing: `tei-embeddings`' image has no arm64 manifest, so the Graviton move made on the database line above is not available here | 276.96<!--FD16--> | 282.51<!--FE4--> |
| Qdrant PVCs | 2 × 50 GB gp3 | 2 × 10 GB gp3 | collection snapshot 496 MB | 9.52<!--FD14--> | 1.90<!--FE5--> |
| Karpenter on Fargate | 2 × 0.5 vCPU / 1 GB (request 300m) | 2 × 0.25 vCPU / 1 GB (request 250m) | controller CPU ≈ 0 at rest (probe) | 41.45<!--FD4--> | 24.46<!--FE6--> |
| Interface VPC endpoints | 2 × 3 AZ (`bedrock`, `bedrock-runtime`) | 1 × 3 AZ: the `bedrock` control-plane endpoint is a defect, not a size | nothing reaches it; the API imports only `bedrockruntime` (errors table) | 52.56<!--FD15--> | 26.28<!--FD47--> |
| Core nodes | 2 × t3.large On-Demand | unchanged | memory never measured; CPU alone would fit t3.medium | 140.16<!--FD2--> | 140.16<!--FD2--> |
| Everything else fixed | | unchanged | | 157.50<!--FD84--> | 157.50<!--FD84--> |
| **C fixed** | | | | **866.79<!--FD27-->** | **753.26<!--FE10-->** |
| Variable at rest | | unchanged | | 10.76<!--FD28--> | 10.76<!--FD28--> |
| **C total** | | | | **877.54<!--FD29-->** | **764.02<!--FE11-->** |

Every row above argues from an observed working set. CUR argues the same case from the billing
side, independently: in the resting hour the six nodes cost $0.8298<!--FD129--> ᴰ (the Floor's three
node lines ÷ 730, and equal to that hour's CUR compute rows to the seventh decimal), and EKS split
cost allocation assigns $0.3360<!--FD131--> of it to pods and emits $0.4938<!--FM58--> as `unused`
— **59.5<!--FD130-->%** of node spend that no pod requested. Split by pool the remainder is 64% on
`apps-serving`, 55% on `database` and 57% on `core`, the same picture everywhere, so the two large
pools hold about three quarters of it by being large rather than by being worse. Inside what *is*
requested, two pods account for nearly all of it: `tei-embeddings` for roughly seven eighths of
what `apps-serving` attributes and `qdrant` for the same share of `database`'s, the rest being
DaemonSets and the monitoring stack.

**This is a lower bound, not measured idleness.** AWS apportions an instance across its pods by
resource *request*, so a pod asking for three cores and using a fifth of one is counted as
requested in full — which is exactly the case for the database line above, where Qdrant requests
a `.large` node and holds 379 MiB. The right-size therefore recovers at least this much and
probably more; the two readings bound the same quantity from opposite sides.

### Retro

- **Expectation** — not held. `apps-serving` is the largest B line at 52.5<!--FD85-->% ($279.82<!--FD18--> of $533.20<!--FD23--> fixed); Qdrant's nodes and volumes are second at 37.7<!--FD86-->% ($200.82<!--FD31-->), short of the predicted majority; the Bedrock endpoints are third at 9.9<!--FD87-->% ($52.56<!--FD15-->). Qdrant's PVC data alone is 1.8<!--FD88-->% ($9.52<!--FD14-->)
- **Attribution coverage** — `M2` reads **25.6<!--FD126-->%** over the Floor's own resting hour, $0.3758642<!--FM57--> of $1.465973<!--FM56--> (re-pulled 2026-09-26; the first read, 14.3%, was over the bootstrap hour and is superseded). It is a reading, not a gate: the 5% threshold it used to carry was removed, because everything here that can be tagged is tagged and the remainder is AWS-managed flat charges. The rise is a defect entering the numerator, not a tagging regression — the CloudWatch vended-log line is $0.1382863<!--FD125--> of it and reads $0 in the bootstrap hour; net of it, 17.9<!--FD127-->%. R5 accounts for the whole gap: 8 non-zero untagged lines, $0.21163 for the hour, every one of them resolving to a Floor row. That explains *why* M2 is high — the lines are AWS-managed and mostly structurally untaggable (EKS control plane, Karpenter's Fargate pod, public IPv4, KMS), and two more (EKS control-plane hours, the LB) are tagged resources whose tag doesn't reach their flat hourly CUR line, a narrow gap worth fixing at the source. **Corrected 2026-09-26**: R5 originally read as an A-or-B allocation and concluded all $0.21163 was Block A. Rewritten as a mapping — untagged money is Floor money seen through the tag column, not separate money to assign — it lands mostly in A but puts the untagged 50 GB gp3 rows in B (Qdrant PVCs) and their leftover twins in the errors table. So the worry in M2's own notes, that folding untagged money into A understates B, was real for this hour. No total moves either way: the mapping changes no dollar, only which existing row a dollar was always in
- **Cost against estimate** — no capture-specific budget was set for this execution; not applicable
- **Month-close revision** — not yet. September closes in October, so K3's second read is still open
- **Not observed** — M3 (node inventory from Prometheus; taken from CUR instead); Qdrant hnsw config (assumed at client default, never read live); EKS control-plane version (terraform default, never read live) → report Coverage
