# 01 · Ingestion concurrency — Metrics

Frozen with the Plan, before the first point. Refs are cited from outside as `01-ingestion/M5`.

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | SQS depth over the window, both queues | `keda_scaler_metrics_value{scaledObject=…}` | ⟨confirmed YYYY-MM-DD⟩ | required · one series per queue, never summed · its derivative is D15 |
| M2 | billable nodes at each moment, by capacity type | `kube_node_labels{label_karpenter_sh_nodepool="apps-compute"}` | ⟨confirmed YYYY-MM-DD⟩ | required · Spot and On-Demand kept apart, they are priced apart · unfiltered it counts the Qdrant node as ingestion capacity and inflates every `$/run` by a plausible constant |
| M3 | node creation timestamp | `kube_node_created` | ⟨confirmed YYYY-MM-DD⟩ | required · warm-up window, open side · node selector as M2 → K1 |
| M4 | first-pod-ready timestamp | `kube_pod_start_time` ⟨confirm⟩ | unconfirmed, name varies by kube-state-metrics version | required · warm-up window, close side · pods owned by the ingestion `ScaledJob`s |
| M5 | worker CPU as a fraction of the frozen limit | `container_cpu_usage_seconds_total`, cAdvisor | ⟨confirmed YYYY-MM-DD⟩ | required · Tier 1 proof · selector `namespace` plus `container!=""` plus `container!="POD"` plus component · read as a rate against the limit in `00-baseline` §2, never as an absolute |
| M6 | worker peak working set | `container_memory_working_set_bytes` | ⟨confirmed YYYY-MM-DD⟩ | required · selector as M5 · source of two guardrail rows |
| M7 | egress bytes, NAT-bound | Cilium eBPF ⟨confirm series⟩ | unconfirmed, must separate NAT-bound from cluster-internal | optional · feeds one line of D20; if unresolved that line is priced from the rate card and marked ᴱ |
| M8 | TEI inference queue depth | `te_queue_size` ⟨confirm⟩ | pending ServiceMonitor | optional · Tier 2 candidate |
| M9 | TEI inference duration | `te_request_inference_duration` ⟨confirm `_bucket` suffix and unit⟩ | pending ServiceMonitor | optional · Tier 2 candidate |
| M10 | Qdrant write and upsert latency | ⟨confirm at `:6333/metrics`⟩ | pending ServiceMonitor | optional · Tier 2 candidate |
| R11 | run log — point id, N, config commit, UTC start and end, interruption count, validity decision | emitted by `run-point.py` into `./data/⟨point⟩.point.md` | active | Prometheus does not know when a run began, and a window reconstructed a week later is a different run |
| R12 | saturation signal — which component sat at its ceiling, and the metric it was read from | read in Grafana at ⟨immediately after each point⟩ · ⟨who⟩ | active | no query returns "the chunker was the bottleneck" · candidates are M5, M8, M10, or the queue not draining despite idle workers on M1 · the only field of the point block the script cannot fill |
| R13 | Qdrant `points_count` at window close | one REST read by `run-point.py` at ⟨window close⟩ | active | completeness check against the frozen corpus count; if it disagrees the denominator lies |
| D14 | docs/min | `00-baseline` §2 unit count ÷ wall time from R11 | active | cross-checked against D15 |
| D15 | drain rate | derivative of M1 | active | catches a run that stalled and recovered rather than draining steadily |
| D16 | node-hours per point | M2 integrated over the window, Spot and On-Demand kept separate | active | |
| D17 | `$/run` | `D16_spot × price_spot + D16_od × price_od`, prices from `00-baseline` §2 | active | a product, not a sum over types, because the NodePool is pinned |
| D18 | `$/1M docs` | `D17 ÷ doc_count × 1e6` | active | the frontier's y-axis |
| D19 | warm-up share | `((M3 → M4) + consolidation tail) ÷ D16` | active | the U-curve mechanism → K1 |
| D20 | marginal decomposition at the sweet spot | D17, M7 and the price basis, split into chunker, indexer, TEI share, warm-up, SQS, S3, NAT | active | components sum to the total · floor lines excluded by definition (`methodology.md` §9) |
| D21 | effective `$/doc` across volumes | `(Block B + D20 × V) ÷ V`, Block B from `00-baseline` §2 Floor | active | Block B rather than C: for a feature on a cluster that exists anyway the question is what this feature costs to keep alive |
| D22 | Fargate equivalent | `vCPU-hours × rate + GB-hours × rate`, from frozen pod requests × D16 | active | the realistic alternative is a different compute mode on the same platform |
