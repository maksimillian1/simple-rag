# 02 · Inference — query path

- **Why this execution exists** — how many queries per second this deployment serves inside the latency target, what the autoscaler does to get there, and what a query costs: how much traffic can we take?
- **Produces** — the sustained query rate, the replica count that rate requires, the query-path constraint, and the marginal cost per thousand queries that report §4 cannot compute itself
- **Expected** — recorded ⟨date⟩, before the first run: ⟨the ceiling is TEI embedding of the query string rather than Qdrant retrieval, because RRF fusion is delegated to the database and costs under 1 ms, while every query pays one full embedding forward pass⟩
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Givens** — `00-baseline` §2, cited from there. The collection is restored from the snapshot taken after `01-ingestion` closed

---

## 1 · Plan

### Axis

- **Varied parameter** — offered arrival rate R in requests per second, set at the load generator with `--rate`. Nothing inside the cluster is edited between points
- **Candidate grid** — R ∈ {5, 25, 50, 100, 200}
- **Sweep order** — coarse to fine: {5, 50, 200}, then two refinement points placed around wherever p95 first approaches the target (`methodology.md` §7). Five points total
- **Held constant** — image digests, the restored collection, Qdrant collection config, the Bedrock stub delay, both scaler triggers and thresholds, `minReplicaCount`, instance types, and every row of `00-baseline` §2 Configuration freeze
- **Not held constant, and measured instead** — API and TEI replicas, and the nodes under them. The autoscaler is the system under test → K2

Replica count is an output here, not an axis. It is set by the scaler in response to load, and
at low arrival rates a higher ceiling changes nothing because no pod is under pressure. The
ceiling is deliberately raised out of reach in `00-baseline` §2 so that it never binds; a point
that reaches it has measured the ceiling instead of the system and is excluded.

Overload is not swept. Driving the generator past capacity makes latency a function of the
backlog rather than of the system, and the p95 then grows with run duration → K3.

### Unit and window

A unit is one search request, complete when the retrieved context is written to the response.

Generation is stubbed at the fixed delay frozen in `00-baseline` §2, and no run calls Bedrock
→ K1. The cost of generation is priced separately from assumed token counts in E18.

Each point runs at one constant offered rate. The window opens once three things are true:
replicas have been stable for ⟨60⟩ s on both deployments, the serving NodePool has been stable
for ⟨60⟩ s, and a further ⟨60⟩ s of warm-up has elapsed. Scaler and node convergence sit inside
the point rather than before it, because both are part of what is being measured. The window
runs ⟨10⟩ min at steady rate and closes when the generator stops.

The load generator runs ⟨inside the cluster on the core node group · outside the VPC⟩; that
choice decides whether NAT and public network latency sit inside the measured number, and it is
frozen with this Plan.

**Points are scheduled one per clock hour** for the same reason as `01-ingestion`
→ `01-ingestion/K6`. Between points the generator stops and both deployments are allowed to
return to their minimum replicas, so each point pays its own scale-out.

No ingestion runs during this execution, except in the contention pass below.

### Metrics

Refs are cited from outside as `02-inference/M2`. M1 through M8 are Prometheus-sourced and gate
their point. M9 and M10 are CUR-sourced and gate the campaign through a cost pass run at least
48 h after the last point. M11 and M12 are optional and gate one claim — whether the ceiling
sits in embedding or in retrieval.

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | requests served per second | `⟨http_requests_total⟩` on the Go API ⟨confirm⟩ | ⟨confirmed YYYY-MM-DD⟩ | required · compared against the offered rate at every point. A shortfall means the generator was the limit and the point is excluded → K3 |
| M2 | request duration distribution | `⟨http_request_duration_seconds_bucket⟩` ⟨confirm⟩ | ⟨confirmed YYYY-MM-DD⟩ | required · histogram, p50 p95 p99 read from buckets, never averaged across the window · generation is stubbed, so this is a retrieval-path number and not an end-to-end SLO → K1 |
| M3 | error rate by status class | same family, status label | ⟨confirmed YYYY-MM-DD⟩ | required · a rate held at the cost of errors is not a sustained rate |
| M4 | Go API and TEI container CPU against the frozen limits | `container_cpu_usage_seconds_total` | ⟨confirmed YYYY-MM-DD⟩ | required · constraint proof, and the reading that works whatever the scaler trigger turns out to be · selector `namespace` plus `container!=""` plus `container!="POD"` plus `component` · read per replica, since replica count moves between points |
| M5 | Qdrant container CPU against its limit | same family, Qdrant pod | ⟨confirmed YYYY-MM-DD⟩ | required · the third component on the query path, and the only one both paths share · Qdrant does not autoscale, so it is the one component whose ceiling cannot be relieved by the scaler · without this the contention pass records that the rate dropped and cannot say whether it ran out of cores or out of page cache |
| M6 | Go API and TEI peak working set | `container_memory_working_set_bytes` | ⟨confirmed YYYY-MM-DD⟩ | required · guardrail source · a serving process holds a steadier working set than a batch worker, so the sampling caveat on `01-ingestion/K3` bites less here |
| M7 | API and TEI replicas over the window | `kube_deployment_status_replicas`, both deployments | ⟨confirmed YYYY-MM-DD⟩ | required · the observed column of this execution and the source of both replica guardrails → K2 · converged value, with the peak and the time to converge from the point's open · equal to `maxReplicaCount` means the ceiling bound and the point is excluded |
| M8 | nodes on the serving pool, by capacity type | `kube_node_labels{label_karpenter_sh_nodepool="apps-serving"}`, split on `label_karpenter_sh_capacity_type` | ⟨confirmed YYYY-MM-DD⟩ | required · the pool is mixed Spot and On-Demand and the split is not optional · a node arriving mid-window means convergence was declared too early and the point is re-run |
| M9 | serving pool cost over the window | CUR 2.0 · `line_item_unblended_cost` where `line_item_line_item_type='Usage'` and `resource_tags_user_tier='apps-serving'`, over the hourly buckets covering the window | ⟨confirmed YYYY-MM-DD⟩ | required for the campaign, blocks no point · gross, before the floor is removed · same instrument and same subtraction as `01-ingestion/M11`, on the same pool → `01-ingestion/K6` |
| M10 | pod-level split of M9 — api, tei, and capacity used by neither | CUR 2.0 split cost allocation columns, grouped by the `component` pod label ⟨confirm column name⟩ | ⟨confirmed YYYY-MM-DD⟩ | required for the campaign · says which of the two deployments the marginal cost went to, which is the cost-side answer to the same question the constraint answers · an allocation rule rather than a measurement → `01-ingestion/K5` |
| M11 | TEI inference duration and queue depth | `te_request_inference_duration` · `te_queue_size` ⟨confirm⟩ | pending ServiceMonitor | optional · separates embedding time from retrieval time inside the p95 · a queue that grows while M7 is still climbing is scaler lag, not a capacity ceiling |
| M12 | Qdrant search latency | ⟨confirm at `:6333/metrics`⟩ | pending ServiceMonitor | optional · the other half of the same split · also the second reading in the contention pass, where CPU headroom with latency rising points at page cache rather than cores |
| R13 | run log — offered rate, UTC window, config commit, stub delay, convergence time, validity decision | emitted by `run-rate.py` into `./data/⟨point⟩.point.md` | active | the window is not recoverable afterwards, and the cost pass reads its windows from here |
| R14 | saturation signal — which component sat at its ceiling | read in Grafana immediately after each point · ⟨who⟩ | active | candidates are TEI CPU, Go API CPU, Qdrant CPU or search latency, the scaler failing to converge, or the generator itself |
| D15 | sustained rate | the highest swept rate holding p95 under ⟨200⟩ ms with M3 under ⟨0.1⟩ % and M1 matching the offered rate | active | the headline number of this execution → K3 |
| D16 | marginal `$/1k queries` | `(M9 − serving pool idle rate × window hours) ÷ queries_served × 1000`, idle rate from `00-baseline` §2 | active | measured, because replicas and nodes move with the axis · the subtraction keeps the always-on minimum out of a marginal figure · at low rates it can round to zero, which is a finding rather than an error |
| D17 | floor share per 1k queries at the sustained rate | `Block B ÷ (D15 × 3600 × 730) × 1000`, Block B from `00-baseline` §2 Floor | active | the other half of what a query costs, and the larger half at low volume · a best case: it assumes the tier runs at D15 continuously, and it grows inversely with utilisation |
| E18 | `$/1k queries`, generation | ⟨n⟩ input and ⟨n⟩ output tokens × the Bedrock rate in `00-baseline` §2 | active | estimated, because the token count is assumed rather than swept and no run called Bedrock · reported beside D16 and D17, never added into either silently |

If M11 and M12 never land, the constraint is named at component granularity from M4 and M5, and
the embedding-versus-retrieval split goes to report Coverage.

### Validity

A point is excluded when the served rate on M1 falls short of the offered rate by more than a
few percent. The generator, not the system, was the limit → K3.

A point is excluded when M7 reaches `maxReplicaCount` on either deployment. The ceiling bound,
and the point describes a configured limit rather than the system.

A point is excluded when the collection differs from the restored snapshot, when the stub delay
differs from the frozen value, or when either scaler trigger or threshold changed. All three
change what the p95 describes.

A point is excluded when its window shares an hourly CUR bucket with another point, or with an
ingestion point → `01-ingestion/K6`.

A point is not trusted when M3 exceeds ⟨0.1⟩ %. Latency measured while requests are failing
describes a system that is already broken.

A point is re-run when M7 or M8 moved during the window. Convergence was declared too early, and
the window contains scale-out rather than steady state.

A point is re-run when a serving node was lost during the window.

### Safeguards

- **Estimated cost and duration** — 5 points × ⟨wall time⟩ · ⟨$⟩ ᴱ, spread over ⟨n⟩ hours by the one-point-per-hour rule
- **Abort condition** — the generator saturates before the system at the lowest rate that shows any latency rise. The measurement is then about the generator, and continuing produces a number about the wrong machine

---

## 2 · Journal

One invocation per point. The script holds a constant rate, waits for replica and node
convergence, times the window, exports Prometheus and emits the point block. It does not read
cost.

```bash
../../scripts/run-rate.py --run inference-r050 --rate 50 --duration 600
```

The cost pass is the same script as `01-ingestion` uses, run once for the campaign:

```bash
../../scripts/aws-cur-report-export.py --execution 02-inference --after 48h
```

### Run ledger

| # | Point | Rate | Window UTC | Commit | Converge | Replicas api / tei | Outcome | Signal | Exported | Cost read |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | inference-r005 | 5 | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨s⟩ | ⟨⟩ / ⟨⟩ | ⟨ok · invalid, ⟨reason⟩⟩ | ⟨⟩ ᴿ | ⟨✓ · —⟩ | ⟨✓ · —⟩ |
| 02 | inference-r050 | 50 | | | | | | | | |
| 03 | inference-r200 | 200 | | | | | | | | |
| 04 | inference-r⟨⟩ | ⟨⟩ | | | | | | | | |
| 05 | inference-r⟨⟩ | ⟨⟩ | | | | | | | | |

### Notes

**Decision after the coarse pass** — ⟨which two refinement points, and the shape that placed them⟩

**#⟨n⟩** — ⟨deviation from the plan, anomaly, mid-run decision, why it was aborted⟩

### Close

- [ ] Saturation identified, or headroom confirmed at the top of the grid.
- [ ] Cost pass run at least 48 h after the last point, and re-run after the month closed if any figure moved.
- [ ] Contention pass run at the point nearest D15.
- [ ] Convergence time recorded at every point, and compared against the window length.
- [ ] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ.
- [ ] Outcome compared against Expected in Retro, inversion included.

---

## 3 · Results

**Finding** — ⟨one sentence: the deployment sustains ⟨R⟩ req/s at p95 = ⟨W⟩ ms on the retrieval
path, on ⟨n⟩ API and ⟨n⟩ TEI replicas, and the ceiling is ⟨component⟩⟩ → report §3.7

### Matrix

| Run | Offered req/s | Served req/s | api / tei replicas | Converge s | p50 ms | p95 ms | p99 ms | Error % | Serving $ | $/1k queries | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #01 | 5 | | ⟨⟩ / ⟨⟩ | | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #02 | 50 | | ⟨⟩ / ⟨⟩ | | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #03 | 200 | | ⟨⟩ / ⟨⟩ | | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #04 | ⟨⟩ | | ⟨⟩ / ⟨⟩ | | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴰ |
| #05 | ⟨⟩ | | ⟨⟩ / ⟨⟩ | | | | | | | ⟨⟩ ᴰ | ⟨⟩ ᴿ |

`Replicas` is M7 at convergence and is an outcome, not a setting → K2. `Serving $` is M9 net of
the floor. `$/1k queries` is D16 and excludes generation.

Every latency column excludes generation, which was stubbed at ⟨n⟩ ms → K1.

- **Sustained rate** — D15 = ⟨⟩ req/s → report §3.7
- **Replicas at that rate** — ⟨n⟩ API, ⟨n⟩ TEI, converged in ⟨s⟩
- **Scaling shape** — ⟨replicas against served rate: linear · sublinear, and where⟩ → report §3.6
- **Reference value** — the `p95 < 200 ms` line in `architecture.md`, which was a design target and not a measurement
- **Condition boundary** — the two scaler triggers, the stubbed generation path, the restored collection, generator placement, and `00-baseline` §2 Envelope
- **Raw data** — `./data/frontier.csv` · chart by `./scripts/plot-rate.py` → `../../assets/`

**Cost at the sustained rate** — D16 = ⟨⟩ marginal, D17 = ⟨⟩ floor share, E18 = ⟨⟩ generation
→ report §4.2

### Contention pass

Repeat the point nearest D15 with ingestion running at the `01-ingestion` guardrail value.
Qdrant serves both paths from one node and one process, and TEI serves both from one deployment,
so a query run against an idle ingestion path measures a state the system is not in during a
backfill. Upsert builds HNSW links on the same cores that serve search, the optimizer keeps
rebuilding segments after ingestion stops, and writes evict from page cache what search reads
back from disk. Those produce the same symptom and take different remedies, which is what M5 and
M12 separate.

- **Sustained rate under ingestion** — ⟨⟩ req/s, against ⟨⟩ without → report §3.8
- **What gave way** — ⟨M5 at its ceiling: cores · M5 with headroom and M12 rising: page cache or optimizer · TEI replicas split between the two paths on M7 · neither, the drop is elsewhere⟩ ᴿ
- **Decision** — ⟨the query guardrail holds · a separate backfill-window guardrail is needed⟩

### Saturation

**Tier 1 — ⟨component⟩ at ⟨R⟩ req/s, run #⟨n⟩**

- **Evidence** — M4 or M5 at the frozen limit, with R14 recorded at the point. If M11 and M12 landed, the p95 is split into embedding and retrieval
- **Relieved by** — ⟨a scaler change if replicas were still climbing · a larger instance type or a Qdrant change if a per-replica limit bound⟩ at ⟨$⟩ ᴰ per month

A ceiling on a component that autoscales is only a ceiling if the scaler had already converged.
M7 is what separates the two, and a point where replicas were still moving proves nothing about
capacity.

No second tier is claimed unless the first was actually relieved and a new ceiling was then
observed (`methodology.md` §8).

### Guardrails

- **Go API `maxReplicaCount` = ⟨n⟩** — from M7 at the sustained rate plus ⟨50⟩ % · `api-scaler` → report §5
- **TEI `maxReplicaCount` = ⟨n⟩** — from M7 at the sustained rate plus ⟨50⟩ % · `tei-embeddings-scaler` → report §5
- **Go API `limits.memory` = ⟨⟩** — from M6 peak plus ⟨30⟩ % · `deploy/k8s/apps/api` → report §5
- **TEI `limits.memory` = ⟨⟩** — from M6 peak plus ⟨30⟩ % · `deploy/k8s/apps/tei` → report §5
- **Query rate alert at ⟨⟩ req/s** — D15 × 0.8 · `prometheus/rules.yaml` → report §5
- **Latency alert at p95 > ⟨⟩ ms for ⟨⟩ min** — from the Matrix · `prometheus/rules.yaml` → report §5
- **Backfill `maxReplicaCount` = ⟨n⟩** — from the contention pass, only if it differs from the `01-ingestion` value → report §5

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — ⟨held · inverted — what actually saturated, in the words that go into the report⟩
- **Cost against estimate** — ⟨⟩
- **What should have been caught before the first run** — ⟨and which validity criterion should have caught it⟩
- **Stub delay** — ⟨did the frozen value sit far enough below the retrieval path to leave the ceiling visible⟩
- **Scaler** — ⟨did replicas converge inside the wait, and did convergence time grow with rate⟩
- **Utilisation** — ⟨how far below D15 does expected production traffic sit, and what that does to D17⟩
- **Back into the kit** — ⟨⟩
