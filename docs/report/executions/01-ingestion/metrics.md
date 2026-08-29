# 01 · Ingestion concurrency — Metrics

Belongs to `index.md` §1 Plan. **Frozen with the Plan, before the first point.** Refs are
cited from outside as `01-ingestion/M5`.

Confirm every name against the live endpoint before writing a query. A wrong name returns NO
DATA and is indistinguishable from a missing scrape target.

## Read from instruments

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | SQS depth over the window, both queues | `keda_scaler_metrics_value{scaledObject=…}` | ⟨confirmed YYYY-MM-DD⟩ | one series per queue, **never summed**. Its derivative is `D15` |
| M2 | billable nodes at each moment, by capacity type | `kube_node_labels{label_karpenter_sh_nodepool="apps-compute"}` | ⟨confirmed YYYY-MM-DD⟩ | Spot and On-Demand kept apart — they are priced apart. Unfiltered it counts the Qdrant node as ingestion capacity and inflates every `$/run` by a plausible-looking constant |
| M3 | node creation timestamp | `kube_node_created` | ⟨confirmed YYYY-MM-DD⟩ | warm-up window, open side · node selector as M2 → `00-baseline/K7` |
| M4 | first-pod-ready timestamp | `kube_pod_start_time` ⟨confirm⟩ | **unconfirmed** — name varies by kube-state-metrics version | warm-up window, close side · pods owned by the ingestion `ScaledJob`s |
| M5 | worker CPU as a fraction of the frozen limit | `container_cpu_usage_seconds_total` (cAdvisor) | ⟨confirmed YYYY-MM-DD⟩ | **Tier 1 proof.** Selector `namespace` + `container!=""` + `container!="POD"` + per component. Read as a rate against the limit frozen in `00-baseline` §2, never as an absolute |
| M6 | worker peak working set | `container_memory_working_set_bytes` | ⟨confirmed YYYY-MM-DD⟩ | selector as M5. Source of two guardrail rows |
| M7 | egress bytes, NAT-bound | Cilium eBPF ⟨confirm series⟩ | ⟨unconfirmed — must separate NAT-bound from cluster-internal⟩ | optional: feeds one line of `D20`. If unresolved that line is priced from the rate card and marked ᴱ |
| M8 | TEI inference queue depth | `te_queue_size` ⟨confirm⟩ | **pending** ServiceMonitor | Tier 2 candidate → `00-baseline/K5` |
| M9 | TEI inference duration | `te_request_inference_duration` ⟨confirm `_bucket` suffix and unit⟩ | **pending** ServiceMonitor | Tier 2 candidate |
| M10 | Qdrant write / upsert latency | ⟨confirm at `:6333/metrics`⟩ | **pending** ServiceMonitor | Tier 2 candidate |

**Required for a point to count** — M1, M2, M3, M4, M5, M6. A point missing any of them has
no cost figure, no mechanism, or no Tier 1, and is not worth its cluster time.

**Optional** — M7 degrades one line of `D20` to estimated · M8, M9, M10 gate Tier 2 and
nothing else.

Query file: `./scripts/queries.txt`, written with confirmed names only · dry run clean ⟨date⟩.
Prometheus retention is ⟨3 d⟩: **export after every point.** Extra points in an export are
harmless; a missing one costs a full re-run.

## Recorded by hand

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| R11 | run log — point id, N, config commit, UTC start and end, interruption count, validity decision | emitted by `run-point.py` at the end of each point into `./data/⟨point⟩.point.md` | active | Prometheus does not know when a run began; a window reconstructed a week later is a different run |
| R12 | saturation signal — which component sat at its ceiling, and the metric it was read from | read in Grafana at ⟨immediately after each point⟩ · ⟨who⟩ | active | no query returns "the chunker was the bottleneck". Candidates: chunker CPU (M5) · TEI queue (M8) · Qdrant write latency (M10) · queue not draining despite idle workers (M1). **The only field of the point block the script cannot fill.** A point with R12 empty still contributes its cost row and nothing to report §3.5 |
| R13 | Qdrant `points_count` at window close | one REST read by `run-point.py` at ⟨window close⟩ | active | completeness check against the frozen corpus count — if it disagrees, the denominator lies |

## Derived

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| D14 | docs/min | `00-baseline` §2 unit count `÷` wall time from R11 | active | cross-checked against D15 |
| D15 | drain rate | derivative of M1 | active | catches a run that stalled and recovered rather than draining steadily |
| D16 | node-hours per point | M2 integrated over the window, **Spot and On-Demand kept separate** | active | |
| D17 | `$/run` | `D16_spot × price_spot + D16_od × price_od`, prices from `00-baseline` §2 | active | a product, not a sum over types — the NodePool is pinned |
| D18 | `$/1M docs` | `D17 ÷ doc_count × 1e6` | active | the frontier's y-axis |
| D19 | warm-up share | `((M3 → M4) + consolidation tail) ÷ D16` | active | the U-curve mechanism → `00-baseline/K7` |
| D20 | marginal decomposition at the sweet spot | `D17` · M7 · price basis — chunker, indexer, TEI share, warm-up, SQS, S3, NAT; components sum to the total | active | **floor lines excluded by definition** (`methodology.md` §9); mixing them inflates the coefficient and corrupts D22 |
| D21 | effective `$/doc` across volumes | `(Block B + D20 × V) ÷ V`, Block B from `00-baseline` §2 Floor | active | Block B, not C: for a feature on a cluster that exists anyway the question is what this feature costs to keep alive |
| D22 | Fargate equivalent | `vCPU-hours × rate + GB-hours × rate`, from frozen pod requests × D16 | active | the realistic alternative — a different compute mode on the same platform |
