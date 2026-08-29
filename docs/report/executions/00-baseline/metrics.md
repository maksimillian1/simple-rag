# Execution · 00 · Baseline — Metrics

Scope: **what is observable** — a property of the system, like a component's version. What a
given run *reads*, with which filters and gating which claim, is method and lives in that
execution's `metrics.md`.

Confirm every name against the live endpoint before writing a query. A wrong name returns NO
DATA and is indistinguishable from a missing scrape target.

---

## Register

Numbers are permanent. A retired metric keeps its ref and gains a status, so references in
older revisions stay resolvable. **Never renumber, never reuse.**

| Range | Component / domain | Added |
| :--- | :--- | :--- |
| E1–E9 | cluster cost and capacity — queues, nodes, warm-up, egress | v1.0 |
| E10–E19 | ingestion workers — chunker, indexer | v1.0 |
| E20–E29 | TEI · embedding service | v1.0 |
| E30–E39 | Qdrant | v1.0 |
| E40–E49 | *reserved* — Go API query path, added with `02-inference` | |
| E50– | *reserved* | |

Status values: *available* · *pending* · *retired in v⟨n⟩* · *superseded by E⟨n⟩*.

> **Runs are named, metrics are numbered.** Executions are `00-baseline`, `01-ingestion`,
> `02-inference`; their points are `⟨name⟩-⟨value⟩` — `ingestion-n04`, `ingestion-n12`.
> Never let one identifier mean both. This is the collision the v0 draft had, where "E1"
> meant a run and a metric on the same page.

**Derived (C) and hand-recorded (R) refs are execution-local** and are cited from outside
with their execution: `01-ingestion C4`. Only E refs are global, because only E refs are
properties of the system.

---

## Cluster cost and capacity · E1–E9

| Ref | Metric | Name as exposed | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| E1 | SQS depth over time, both queues | `keda_scaler_metrics_value` | available | its derivative is the drain-rate cross-check |
| E2 | node count by instance type and capacity type | `kube_node_labels` | available | integrated over a window → node-hours |
| E3 | node creation timestamp | `kube_node_created` | available | warm-up window, open side |
| E4 | first-pod-ready timestamp | `kube_pod_start_time` ⟨confirm⟩ | available · **name unconfirmed** | warm-up window, close side. Name varies by kube-state-metrics version |
| E5 | egress bytes, NAT-bound | Cilium eBPF ⟨confirm series⟩ | available | feeds the NAT per-GB line |
| E6–E9 | *reserved* | | | |

E2 as used:

```
count by (label_node_kubernetes_io_instance_type, label_karpenter_sh_capacity_type) (kube_node_labels)
```

Capacity type matters: Spot and On-Demand node-hours are priced separately and must never be
summed before pricing.

## Ingestion workers · E10–E19

| Ref | Metric | Name as exposed | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| E10 | container CPU rate — chunker, indexer | `container_cpu_usage_seconds_total` (cAdvisor) | available | **the Tier 1 proof, scraped today** |
| E11 | working set / peak RSS — chunker, indexer | `container_memory_working_set_bytes` | available | source of two guardrail rows |
| E12–E19 | *reserved* | | | |

Read as a rate against the container's CPU limit, not as an absolute — "pinned" means at the
limit, and the limit is frozen in `index.md` §2.

## TEI · E20–E29

| Ref | Metric | Name as exposed | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| E20 | inference queue depth | `te_queue_size` ⟨confirm⟩ | **pending** ServiceMonitor | Tier 2 candidate |
| E21 | inference duration | `te_request_inference_duration` ⟨confirm⟩ | **pending** ServiceMonitor | histogram — confirm the `_bucket` suffix and unit |
| E22–E29 | *reserved* | | | |

## Qdrant · E30–E39

| Ref | Metric | Name as exposed | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| E30 | write / upsert latency | ⟨confirm at `:6333/metrics`⟩ | **pending** ServiceMonitor | Tier 2 candidate |
| E31–E39 | *reserved* | | | |

---

## Pending is not blocking

E20, E21 and E30 gate **report §3.5 Tier 2 only**. Tier 1 reads from E10, which is available
today. `01-ingestion` starts without them; if the ServiceMonitors land before the refinement
points, Tier 2 is claimable from the points that have them. If they never land, one tier is
reported and the second goes to the report's out-of-scope table — which is what the report's
own rule already requires of an unproven tier.

Add via `ServiceMonitor` in each component's namespace with `labels.release` matching the
Helm release, then verify `up{job="…"}` and copy the real name into the table above.

---

## Mandatory filtering

Metrics that mix several producers and cannot be split after the fact. Filter in the query
file, never in the analysis.

| Ref | Mixes | Required selector |
| :--- | :--- | :--- |
| E1 | both ingestion queues, and any other KEDA scaler in the cluster | `scaledObject` / `scaler` label per queue — one series per queue, never summed |
| E2 | every NodePool, including permanent ones | `label_karpenter_sh_nodepool="apps-compute"` for run node-hours; the others are floor, not run |
| E3, E4 | all nodes and all pods | node selector as E2 · pod selector by owning `ScaledJob` |
| E10, E11 | every container in the cluster, plus pause containers | `namespace` + `container!=""` + `container!="POD"` + per-component selector |
| E5 | cluster-internal traffic alongside NAT-bound egress | ⟨resolve — `index.md` §7.5⟩ |

Unfiltered E2 counts the Qdrant node as ingestion capacity and inflates `$/run` by a
constant that looks plausible at every point.

---

## Deliberately not observable

| What | Why it is not needed |
| :--- | :--- |
| Qdrant `points_count` as a Prometheus series | One value at the end of a run, read over REST by `run-point.py`. A time series of it answers no question the report asks |
| Node warm-up sub-phases — provisioning, image pull, runtime init | Report §3.4 needs the overhead *share*, not its attribution |
| Per-execution worker exit summaries | Document counts come from the frozen corpus, drain rate from E1, node loss from `run-point.py`'s node-set watch |
| Go API request metrics | No query-path run consumes them until `02-inference`. Range E40–E49 is reserved |
| Karpenter controller metrics | 15-minute timebox in `index.md` §7.2. Free insurance on interruption events; not a dependency |
| Qdrant RSS as a series | One `kubectl top pod` reading at teardown (`index.md` §8) sizes the instance class. A series of it would not change the instance |

> Instrumentation without a consumer generates work rather than evidence. Add it together
> with the run that needs it.

---

## Renumbering note — v0 draft → v1.0

The pre-framework inventory numbered E1–E9 by acquisition order, which collided with run
names and left no room to add a component. Renumbered **once**, before the first run, into
per-component ranges. From v1.0 onward the rule above applies: never again.

| v0 ref | v1.0 ref | |
| :--- | :--- | :--- |
| E1 SQS depth | E1 | |
| E2 node count | E2 | |
| E3 warm-up window | **E3 + E4** | split — two series, two names to confirm |
| E4 egress | E5 | |
| E5 worker CPU | **E10** | |
| E6 worker RSS | **E11** | |
| E7 TEI queue | **E20** | |
| E8 TEI duration | **E21** | |
| E9 Qdrant latency | **E30** | |
| P1–P3 (Cost Explorer) | — | not metrics; `index.md` §7.4, idle window only |
| C1–C9 | `01-ingestion` C1–C9 | execution-local |
| C10 vector memory arithmetic | — | a given, not a finding: `index.md` §5 note |
| R1 price snapshot | — | `index.md` §4 |
| R2 corpus profile | — | `index.md` §3 |
| R3 run log · R4 saturation | `01-ingestion` R1 · R2 | execution-local |
| R5 teardown | — | `index.md` §8 |

Delete this table at v1.1, when no draft referencing v0 numbers is still open.
