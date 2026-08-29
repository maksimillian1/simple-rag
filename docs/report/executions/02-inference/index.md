# 02 · Inference — query path

- **Why this execution exists** — how many queries per second this retrieval configuration serves before latency breaks, and what a query costs: how much traffic can we take?
- **Produces** — the sustained query rate at the latency target, the query-path constraint, and the marginal cost per thousand queries that report §4 cannot compute itself
- **Expected** — recorded ⟨date⟩, before the first run: ⟨the ceiling is TEI embedding of the query string rather than Qdrant retrieval, because RRF fusion is delegated to the database and costs under 1 ms, while every query pays one full embedding forward pass⟩
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Givens** — `00-baseline` §2, cited from there. The collection is restored from the `00-baseline` snapshot taken after `01-ingestion` closed

---

## 1 · Plan

### Axis

- **Varied parameter** — offered arrival rate R, in requests per second, set at the load generator
- **Candidate grid** — R ∈ {⟨5, 25, 50, 100, 200⟩}
- **Sweep order** — coarse to fine: the two ends and one midpoint, then two refinement points placed by the shape those three produce (`methodology.md` §7)
- **Held constant** — Go API replicas, TEI replicas, Qdrant collection config, image digests, the restored collection, and every row of `00-baseline` §2 Configuration freeze
- **Second pass** — replicas, only if the first pass shows the ceiling is a replica count rather than a per-replica limit

### Unit and window

A unit is one search request, complete when the retrieved context is written to the response.
Generation in Bedrock is outside the unit. Bedrock runs under an account-level quota, so a rate
sweep that includes it measures the provider's throttle rather than this configuration. The cost
of generation is priced separately from token counts in E14.

The window opens ⟨60⟩ s after the generator reaches the target rate, so connection ramp and
warm-up are excluded. It closes when the generator stops. The load generator runs ⟨inside the
cluster on the core node group · outside the VPC⟩; that choice decides whether NAT and public
network latency sit inside the measured number, and it is frozen with this Plan.

### Metrics

Refs are cited from outside as `02-inference/M2`.

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | requests served per second | `⟨http_requests_total⟩` on the Go API ⟨confirm⟩ | ⟨confirmed YYYY-MM-DD⟩ | required · compared against the offered rate to prove the generator was not the limit |
| M2 | request duration distribution | `⟨http_request_duration_seconds_bucket⟩` ⟨confirm⟩ | ⟨confirmed YYYY-MM-DD⟩ | required · histogram, p50 p95 p99 read from buckets, never averaged across the window |
| M3 | error rate by status class | same family, status label | ⟨confirmed YYYY-MM-DD⟩ | required · a rate held at the cost of errors is not a sustained rate |
| M4 | Go API and TEI container CPU against the frozen limits | `container_cpu_usage_seconds_total` | ⟨confirmed YYYY-MM-DD⟩ | required · constraint proof · selector `namespace` plus `container!=""` plus `container!="POD"` plus component |
| M5 | Go API and TEI peak working set | `container_memory_working_set_bytes` | ⟨confirmed YYYY-MM-DD⟩ | required · guardrail source |
| M6 | billable nodes on the serving pool | `kube_node_labels{label_karpenter_sh_nodepool="apps-serving"}` | ⟨confirmed YYYY-MM-DD⟩ | required · without it there is no cost figure |
| M7 | TEI inference duration and queue depth | `te_request_inference_duration` · `te_queue_size` ⟨confirm⟩ | pending ServiceMonitor | optional · separates embedding time from retrieval time inside the p95 |
| M8 | Qdrant search latency | ⟨confirm at `:6333/metrics`⟩ | pending ServiceMonitor | optional · the other half of the same split |
| R9 | run log — offered rate, replica counts, UTC window, config commit, validity decision | emitted by `run-rate.py` into `./data/⟨point⟩.point.md` | active | the window is not recoverable afterwards |
| R10 | saturation signal — which component sat at its ceiling | read in Grafana immediately after each point · ⟨who⟩ | active | candidates are TEI CPU, Go API CPU, Qdrant search latency, or the generator itself |
| D11 | sustained rate | the highest swept rate holding p95 under ⟨200⟩ ms with M3 under ⟨0.1⟩ % | active | the headline number of this execution |
| D12 | node-hours over the window | M6 integrated over the window | active | |
| D13 | `$/1k queries`, compute only | `(D12 × price) ÷ queries_served × 1000` | active | floor lines excluded; this is spend above the always-on replicas |
| E14 | `$/1k queries`, generation | ⟨n⟩ input and ⟨n⟩ output tokens × the Bedrock rate in `00-baseline` §2 | active | estimated, because the token count is assumed rather than swept · reported beside D13 and never added into it silently |

M7 and M8 gate one claim: whether the ceiling sits in embedding or in retrieval. The campaign
starts without them. If they never land, the constraint is named at component granularity from
M4 and the split goes to report Coverage.

The query file is `./scripts/queries.txt`, dry run clean ⟨date⟩. Export runs after every point;
Prometheus retention is ⟨3 d⟩.

### Validity

A point is excluded when the served rate falls short of the offered rate by more than a few
percent. That means the generator, not the system, was the limit.

A point is excluded when the collection differs from the restored snapshot, or when replica
counts moved during the window.

A point is not trusted when the error rate exceeds ⟨0.1⟩ %. Latency measured while requests are
failing describes a system that is already broken.

A point is re-run when a serving node was lost during the window.

### Safeguards

- **Estimated cost and duration** — 5 points × ⟨wall time⟩ · ⟨$⟩ ᴱ
- **Abort condition** — the generator saturates before the system at the lowest rate that shows any latency rise. The measurement is then about the generator, and continuing produces a number about the wrong machine

---

## 2 · Journal

```bash
../../scripts/run-rate.py --run inference-r050 --rate 50 --duration ⟨s⟩
```

### Run ledger

| # | Point | Window UTC | Commit | Outcome | Signal | Exported |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | inference-r⟨⟩ | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨ok · aborted, ⟨reason⟩ · invalid, ⟨reason⟩⟩ | ⟨component at its ceiling · headroom⟩ ᴿ | ⟨✓ · —⟩ |
| 02 | inference-r⟨⟩ | | | | | |
| 03 | inference-r⟨⟩ | | | | | |
| 04 | inference-r⟨⟩ | | | | | |
| 05 | inference-r⟨⟩ | | | | | |

### Notes

**Decision after the coarse pass** — ⟨which two refinement points, and the shape that placed them⟩

**#⟨n⟩** — ⟨deviation from the plan, anomaly, mid-run decision, why it was aborted⟩

### Close

- [ ] Saturation identified, or headroom confirmed at the top of the grid.
- [ ] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ.
- [ ] Outcome compared against Expected in Retro, inversion included.

---

## 3 · Results

**Finding** — ⟨one sentence: the configuration sustains ⟨R⟩ req/s at p95 = ⟨W⟩ ms, and the
ceiling is ⟨component⟩⟩ → report §3.7

### Matrix

| Run | Offered req/s | Served req/s | p50 ms | p95 ms | p99 ms | Error % | Node-h | $/1k queries | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #01 | ⟨⟩ | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #02 | ⟨⟩ | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #03 | ⟨⟩ | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #04 | ⟨⟩ | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #05 | ⟨⟩ | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |

- **Sustained rate** — D11 = ⟨⟩ req/s → report §3.7
- **Reference value** — the `p95 < 200 ms` line in `architecture.md`, which was a design target and not a measurement
- **Condition boundary** — fixed replica counts, the restored collection, generator placement, and `00-baseline` §2 Envelope
- **Raw data** — `./data/frontier.csv` · chart by `./scripts/plot-rate.py` → `../../assets/`

**Cost** — D13 = ⟨⟩ compute, E14 = ⟨⟩ generation → report §4.2

### Contention pass

Repeat the point nearest D11 with ingestion running at the `01-ingestion` guardrail value.
Qdrant serves both paths from one node, so a query run against an idle ingestion path measures
a state the system is not in during a backfill.

- **Sustained rate under ingestion** — ⟨⟩ req/s, against ⟨⟩ without → report §3.8
- **Decision** — ⟨the query guardrail holds · a separate backfill-window guardrail is needed⟩

### Saturation

**Tier 1 — ⟨component⟩ at ⟨R⟩ req/s, run #⟨n⟩**

- **Evidence** — M4 at the frozen limit, with R10 recorded at the point. If M7 and M8 landed, the p95 is split into embedding and retrieval
- **Relieved by** — ⟨replica increase⟩ at ⟨$⟩ ᴰ per month

No second tier is claimed unless the first was actually relieved and a new ceiling was then
observed (`methodology.md` §8).

### Guardrails

- **Go API `replicas` = ⟨n⟩** — from D11 · `deploy/k8s/apps/api` → report §5
- **TEI `replicas` = ⟨n⟩** — from the constraint above · `deploy/k8s/apps/tei` → report §5
- **Query rate alert at ⟨⟩ req/s** — D11 × 0.8 · `prometheus/rules.yaml` → report §5
- **Latency alert at p95 > ⟨⟩ ms for ⟨⟩ min** — from the Matrix · `prometheus/rules.yaml` → report §5
- **Backfill `maxReplicaCount` = ⟨n⟩** — from the contention pass, only if it differs from the `01-ingestion` value → report §5

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — ⟨held · inverted — what actually saturated, in the words that go into the report⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught before the first run** — ⟨and which validity criterion should have caught it⟩
- **Back into the kit** — ⟨⟩
