# 01 · Ingestion concurrency — Metrics

Frozen with the Plan, before the first point. Refs are cited from outside as
`01-ingestion/M6`.

Two source families with different lifetimes. Prometheus-sourced refs are perishable:
retention is ⟨3 d⟩ and a window not exported inside it is gone, so every one of them gates a
point at the moment it closes. AWS-sourced refs are re-readable for months and gate the
campaign rather than a point.

Required refs are M1 through M8. A point missing any of them has no cost figure, no
mechanism, or no Tier 1, and is not worth its cluster time. M9 is required for the campaign
and blocks no point. M10 through M13 are optional: M10 through M12 gate the second
constraint tier and nothing else, M13 confirms one sizing number once, so the campaign
starts without them rather than waiting for the ServiceMonitors.

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | SQS depth over the window, both queues | `keda_scaler_metrics_value{scaledObject=…}` | ⟨confirmed YYYY-MM-DD⟩ | required · one series per queue, never summed · its shape is the drain check in §1 Validity |
| M2 | billable nodes at each moment, by capacity type | `kube_node_labels{label_karpenter_sh_nodepool="apps-compute"}`, kept split on `label_karpenter_sh_capacity_type` | ⟨confirmed YYYY-MM-DD⟩ | required · Spot and On-Demand are priced apart and must stay apart all the way to D19 · unfiltered by nodepool it counts the Qdrant node as ingestion capacity and inflates every `$/run` by a plausible constant |
| M3 | node creation timestamp | `kube_node_created` | ⟨confirmed YYYY-MM-DD⟩ | required · warm-up window, open side · node selector as M2 → K1 |
| M4 | worker container start timestamp | `container_start_time_seconds`, cAdvisor | ⟨confirmed YYYY-MM-DD⟩ | required · warm-up window, close side · cAdvisor rather than kube-state-metrics: pods of completed Jobs are garbage-collected and their series disappear mid-window, while a container series survives as long as the node does. M3 → M4 is scheduling plus image pull; runtime initialisation after start shows as the lag to first non-zero CPU on M6 |
| M5 | worker concurrency actually reached | `kube_job_status_active`, both ScaledJobs | ⟨confirmed YYYY-MM-DD⟩ | required · the axis is a ceiling, not a setting. If Spot capacity is short, a point set to N=24 runs at whatever was granted and lands in the matrix under 24 · peak and time-weighted mean, both recorded |
| M6 | worker CPU as a fraction of the frozen limit | `container_cpu_usage_seconds_total`, cAdvisor | ⟨confirmed YYYY-MM-DD⟩ | required · Tier 1 proof · selector `namespace` plus `container!=""` plus `container!="POD"` plus component · read as a rate against the limit in `00-baseline` §2, never as an absolute |
| M7 | worker peak working set | `container_memory_working_set_bytes`, exported at ⟨5 s⟩ | ⟨confirmed YYYY-MM-DD⟩ | required · selector as M6 · source of two guardrail rows. A SPLADE forward pass spikes for less than one scrape interval, so this is a lower bound on the true peak → K3. Exported at a finer step than the rest of the query file for that reason |
| M8 | container terminations by reason | `kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}` | ⟨confirmed YYYY-MM-DD⟩ | required · exists to bound M7 · zero OOM at the frozen limit makes that limit a proven ceiling whether or not the scrape caught the spike; a non-zero count invalidates the guardrail derived from M7 and the limit is raised rather than fitted |
| M9 | NAT-bound egress bytes over the window | CloudWatch `NATGateway BytesOutToDestination`, ⟨gateway id⟩ | ⟨confirmed YYYY-MM-DD⟩ | required for the campaign, blocks no point · re-readable for months, unlike everything above it · Prometheus cannot serve this: Cilium does not separate NAT-bound from cluster-internal, and S3 and SQS leave through VPC endpoints, so what remains is model weights pulled per job → K4 · feeds one line of D22 |
| M10 | TEI inference queue depth | `te_queue_size` ⟨confirm⟩ | pending ServiceMonitor | optional · Tier 2 candidate |
| M11 | TEI inference duration | `te_request_inference_duration` ⟨confirm `_bucket` suffix and unit⟩ | pending ServiceMonitor | optional · Tier 2 candidate |
| M12 | Qdrant write and upsert latency | ⟨confirm at `:6333/metrics`⟩ | pending ServiceMonitor | optional · Tier 2 candidate |
| M13 | Qdrant working set at window close | `container_memory_working_set_bytes`, Qdrant pod | ⟨confirmed YYYY-MM-DD⟩ | optional · read once, at the highest-N point, against a loaded collection · the measured half of the pair with D25 · meaningless on the baseline idle window, where the collection is empty |
| R14 | run log — point id, N, config commit, UTC start and end, interruption count, validity decision | emitted by `run-point.py` into `./data/⟨point⟩.point.md` | active | Prometheus does not know when a run began, and a window reconstructed a week later is a different run |
| R15 | saturation signal — which component sat at its ceiling, and the metric it was read from | read in Grafana at ⟨immediately after each point⟩ · ⟨who⟩ | active | no query returns "the chunker was the bottleneck" · candidates are M6, M10, M12, or the queue not draining on M1 despite workers idle on M5 · the only field of the point block the script cannot fill |
| R16 | Qdrant point count at window close | `POST /collections/⟨name⟩/points/count` with `exact=true`, by `run-point.py` | active | completeness check against the frozen corpus count; if it disagrees the denominator lies · the estimate on `GET /collections/⟨name⟩` lags indexing and is not used here |
| D17 | docs/min | `00-baseline` §2 unit count ÷ wall time from R14 | active | |
| D18 | node-hours per point, by capacity type | M2 integrated over the window, Spot and On-Demand kept separate | active | the poll-integrated node-seconds in the point block is a single unsplit scalar and is a sanity check against the sum, not an input to D19 |
| D19 | `$/run` | `D18_spot × price_spot + D18_od × price_od`, prices from `00-baseline` §2 | active | a product, not a sum over types, because the NodePool is pinned |
| D20 | `$/1M docs` | `D19 ÷ doc_count × 1e6` | active | the frontier's y-axis |
| D21 | warm-up share | `((M3 → M4) + consolidation tail) ÷ D18` | active | the U-curve mechanism → K1 |
| D22 | marginal decomposition at the sweet spot | D19, M9 and the price basis, split into chunker, indexer, TEI share, warm-up, SQS, S3, NAT | active | components sum to the total · floor lines excluded by definition (`methodology.md` §9) |
| D23 | effective `$/doc` across volumes | `(Block B + D22 × V) ÷ V`, Block B from `00-baseline` §2 Floor | active | Block B rather than C: for a feature on a cluster that exists anyway the question is what this feature costs to keep alive |
| D24 | Fargate equivalent | `vCPU-hours × rate + GB-hours × rate`, from frozen pod requests × D18 | active | the realistic alternative is a different compute mode on the same platform · prices the same work at Fargate rates and does not model Fargate cold start, which would raise it → K5 |
| D25 | Qdrant vector memory | `dims × bytes_per_dim × points × (1 + hnsw overhead)`, points from R16 at the highest-N point | active | sizing arithmetic, not a finding; no run varies it · compared once against M13 to confirm the instance class behind the Qdrant Floor line in `00-baseline` §2 · under INT8 scalar quantization the in-RAM copy is 1 byte per dimension and the float32 originals sit on disk, so reading `bytes_per_dim` as 4 overstates it fourfold → K3 · a disagreement here is a baseline revision, not a row in this execution's Results |
