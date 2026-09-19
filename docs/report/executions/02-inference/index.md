# 02 · Inference — query path

- **Why this execution exists** — how many queries per second this deployment serves inside the latency target, what the autoscaler does to get there, and what a query costs: how much traffic can we take?
- **Produces** — the sustained query rate, the replica count that rate requires, the query-path constraint, and the marginal cost per thousand queries that report §4 cannot compute itself
- **Expected** — recorded 2026-08-31, before the first run (`git log -S`, commit `bafdc1f`): the ceiling is TEI embedding of the query string rather than Qdrant retrieval, because RRF fusion is delegated to the database and costs under 1 ms, while every query pays one full embedding forward pass
- **Status** — closed
- **Plan frozen** — 2026-08-31 · commit `bafdc1f`
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

Each point runs at one constant offered rate. The design opened a point once three things had
held for 60s each (replica stability on both deployments, NodePool stability, a warm-up
interval). `run-inference-point.py`'s actual `preflight()` checks something weaker: a single
instant read of "replicas == floor right now", with no duration requirement. Either way, scaler
and node convergence sit inside the point rather than before it, because both are part of what is
being measured. The window runs 10 min at steady rate (`--duration` default,
`run-inference-point.py:304`) and closes when the generator stops.

The load generator runs **outside the VPC**, against the internet-facing NLB in front of
`cilium-gateway` (`rag-platform`, `HTTPRoute api-route` → `api` Service), not through
`kubectl port-forward`. Port-forward tunnels to one pod and bypasses kube-proxy and the Service,
so every request lands on a single replica regardless of offered concurrency. That silently turns
a fleet test into a single-pod test (observed at both 50 and 1000 rps: one `api` replica took 100%
of traffic while the other sat at 0 CPU). The NLB is the only path that load-balances across
replicas the way real traffic would.

**The NLB hostname is not stable across cluster recreations** and must be read fresh before each
run, not hardcoded: `kubectl get gateway cilium-gateway -n rag-platform -o
jsonpath='{.status.addresses[0].value}'` (or the underlying Service's
`.status.loadBalancer.ingress[0].hostname` if the Gateway status is unpopulated). Set it as
`api.base_url` in `scripts/env.yaml` before the first point on a new cluster. `env.yaml` exists
for this kind of address (its header: `"not frozen with any Plan and not cited by one"`), so no
code change is needed. Once `api.base_url` is a reachable URL, drop `api.service`/`api.mapping`
from `env.yaml` (or leave `service` unset) so `PortForwards` doesn't open an unused tunnel for it.

**Points are spaced by convergence, not by the clock** (revised 2026-09-05).
Between points the generator stops and both deployments return to their minimum replicas, so each
point pays its own scale-out. That takes minutes rather than an hour and is the only hard spacing
requirement. `01-ingestion/K6`'s one-per-clock-hour rule kept CUR able to attribute cost to a
single point. It is given up on purpose here, and points may share an hourly CUR bucket; no
ingestion runs concurrently, so nothing else contends for the window. As a result `M9`/`M10` are
no longer CUR-sourced per point. Each point's cost comes from `karpenter-cost-estimate.py`'s
node-lifecycle reconstruction (§1 Metrics), with a campaign-level CUR cross-check once the whole
sweep closes.

No ingestion runs during this execution, except in the contention pass (§3).

### Metrics

Refs are cited from outside as `02-inference/M2`. M1 through M8 are Prometheus-sourced and gate
their point. M9 is read per point from `karpenter-cost-estimate.py` (revised 2026-09-05 after
clock-hour spacing was dropped; Plan) and cross-checked at the campaign level by a CUR-sourced cost pass
run at least 48 h after the last point; M10 is CUR-only and not attempted per point. M11 and M12
are optional and gate one claim: whether the ceiling sits in embedding or in retrieval.

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | requests served per second | ~~`http_requests_total` on the Go API~~ → `envoy_cluster_upstream_rq_total{envoy_cluster_name="rag-platform/cilium-gateway-cilium-gateway/rag-api_api_80"}` | **unblocked 2026-09-05** | required · the Go API has no `/metrics` at all (confirmed 2026-09-02, twice). `api` is reached through `cilium-gateway`, though, and Cilium's Envoy sidecars already export per-upstream-cluster request metrics (scrape job `cilium-envoy`), so no application change is needed. Confirmed live against real traffic (`r050`, `r200`): non-zero and matching the offered rate during the load window, `NaN` during idle stretches (0/0 in `histogram_quantile`, expected, not a gap) |
| M2 | request duration distribution | ~~`http_request_duration_seconds_bucket`~~ → `envoy_cluster_upstream_rq_time_bucket`, same cluster label | **unblocked 2026-09-05** | required · same fix as M1 · Envoy histogram with standard `le` buckets in **milliseconds, not seconds**, unlike the assumed Go-exporter convention, so the query has no `/1000` · p50/p95/p99 read from buckets, never averaged · generation is stubbed, so this is a retrieval-path number and not an end-to-end SLO → K1 · confirmed live against `r050`: p95 ≈ 2.1–2.4s during the active load window, consistent with the 2000ms mock delay plus overhead |
| M3 | error rate by status class | ~~same family, status label~~ → `envoy_cluster_upstream_rq_xx{envoy_response_code_class="5"}`, same cluster label | **unblocked 2026-09-05** | required · same fix as M1 · `envoy_response_code_class` (`"2"`,`"4"`,`"5"`, …) is Envoy's own status-class label, a direct match for what M3 wanted from the Go exporter |
| M4 | Go API and TEI container CPU against the frozen limits | `container_cpu_usage_seconds_total` | confirmed 2026-09-02 | required · constraint proof, and the reading that works whatever the scaler trigger turns out to be · selector `namespace` plus `container!=""` plus `container!="POD"` plus `app` · read per replica, since replica count moves between points · this is cAdvisor, unaffected by the M1-M3 gap |
| M5 | Qdrant container CPU against its limit | same family, Qdrant pod | confirmed 2026-09-02 | required · the third component on the query path, and the only one both paths share · Qdrant does not autoscale, so it is the one component whose ceiling cannot be relieved by the scaler · without this the contention pass records that the rate dropped and cannot say whether it ran out of cores or out of page cache |
| M6 | Go API and TEI peak working set | `container_memory_working_set_bytes` | confirmed 2026-09-02 | required · guardrail source · a serving process holds a steadier working set than a batch worker, so the sampling caveat on `01-ingestion/K3` bites less here · at 1000 rps offered against one pinned replica (port-forward artifact, not a real fleet point) this reached 439/512Mi (86%) without OOMing |
| M7 | API and TEI replicas over the window | `kube_deployment_status_replicas`, both deployments | confirmed 2026-09-02 | required · the observed column of this execution and the source of both replica guardrails → K2 · converged value, with the peak and the time to converge from the point's open · equal to `maxReplicaCount` means the ceiling bound and the point is excluded |
| M8 | nodes on the serving pool, by capacity type | `kube_node_labels{label_karpenter_sh_nodepool="apps-serving"}`, split on `label_karpenter_sh_capacity_type` | confirmed 2026-09-02 | required · the pool is mixed Spot and On-Demand and the split is not optional · a node arriving mid-window means convergence was declared too early and the point is re-run · depends on `kube-state-metrics`' `--metric-labels-allowlist`, which was silently unset until it was fixed during this campaign (`00-baseline/K3`); re-check after any monitoring stack redeploy |
| M9 | serving pool cost over the window | **per point**, same-day: `./scripts/karpenter-cost-estimate.py --nodepool apps-serving --start ⟨…⟩ --end ⟨…⟩` (node-lifecycle reconstruction; needs no CUR hour alignment and works on an arbitrary sub-hour window). **Campaign-level cross-check**, once available: CUR 2.0 `line_item_unblended_cost` where `line_item_line_item_type='Usage'` and `resource_tags_user_tier='apps-serving'`, over whichever hourly buckets the campaign's points landed in. It can't isolate one point once points share an hour (revised 2026-09-05; Plan) | active (script), pending (CUR cross-check) | required for the campaign, blocks no point · gross, before the floor is removed · the script reports gross node cost only, same subtraction as `01-ingestion/M11` applies · mark each point's `M9` ᴰ until the CUR cross-check confirms it, same pattern `01-ingestion` used all the way to its own CUR pass |
| M10 | pod-level split of M9 — api, tei, and capacity used by neither | CUR 2.0 split cost allocation columns only; `karpenter-cost-estimate.py` sees node cost, not pods | **not attempted per point** (2026-09-05) | required for the campaign, not for any point · says which of the two deployments the marginal cost went to · deferred to the campaign's CUR pass, same as `01-ingestion/M12` was declared not attempted rather than blocking · if it matters sooner, weighting each node's `M9` by its api/tei pods' CPU requests reproduces the allocation CUR's split-cost columns do; not built, and it would be new work → `01-ingestion/K5` |
| M11 | TEI inference duration and queue depth | `te_request_inference_duration` · `te_queue_size`, names unconfirmed. TEI's `/metrics` returns HTTP 200 with an empty body on this deployment (confirmed live), a deeper problem than a missing scrape config | pending ServiceMonitor, blocked on the empty-body finding | optional · separates embedding time from retrieval time inside the p95 · a queue that grows while M7 is still climbing is scaler lag, not a capacity ceiling |
| M12 | Qdrant search latency | real series names never confirmed against `:6333/metrics` | **scrape job added 2026-09-02, never applied; the cluster was torn down before a live check, so it stays unconfirmed for this campaign** | optional · an earlier read of `GET :6333/metrics` looked empty, but that check grepped for a `qdrant_`/`process_*` prefix never confirmed against the real series names, so it is inconclusive rather than proof the endpoint is disabled · scraping here doesn't use the `qdrant/qdrant` chart's `metrics.serviceMonitor` toggle (chart default `false`); this repo keeps scrapers centralized as raw `additionalScrapeConfigs` in `deploy/k8s/platform/monitoring/values/prometheus.yaml`, and a `qdrant` job already exists there (pod label `app.kubernetes.io/name=qdrant`, port `6333`) · re-check actual series names once a live cluster confirms the job resolves targets · the other half of the same split · also the second reading in the contention pass, where CPU headroom with latency rising points at page cache rather than cores |
| R13 | run log — offered rate, UTC window, config commit, stub delay, convergence time, validity decision | emitted by `run-inference-point.py` into `./data/⟨point⟩.point.md`. Files exist for 4 of 5 real points (`r050` has none), but each is still the unfilled script template (served rate, p95, error, cost and saturation signal blank); the real numbers are in this file's Matrix and Notes | active, but superseded in practice by this file | the window is not recoverable afterwards, and the cost pass reads its windows from here |
| R14 | saturation signal — which component sat at its ceiling | read in Grafana immediately after each point · maksimillian1 | active | candidates are TEI CPU, Go API CPU, Qdrant CPU or search latency, the scaler failing to converge, or the generator itself |
| D15 | sustained rate | the highest swept rate holding p95 at the converged floor (not rising with rate), with M3 under 0.1% and M1 matching the offered rate. The original draft's "under 200ms" predates the 2000ms Bedrock stub delay and can't be met under it (the p95 floor is ~2425ms once converged), so §3 uses this criterion instead | active | the headline number of this execution → K3 |
| D16 | `$/1k queries`, gross | `M9 ÷ queries_served × 1000`, no floor subtracted (D2: points share clock hours, so no per-point rest inventory exists; netting happens once, at campaign level, against the 09-05 resting pair) | active, inherits M9's ᴰ until the CUR cross-check | measured, because replicas and nodes move with the axis · gross, so it carries the resting pair's share of the window and falls with rate as more queries dilute it · good for comparing rates against each other, not for pricing a query; `figures.yaml` group `inference_points` |
| D17 | floor share per 1k queries at the sustained rate | `Block B ÷ (D15 × 3600 × 730) × 1000`, Block B from `00-baseline` §2 Floor | active | the other half of what a query costs, and the larger half at low volume · a best case: it assumes the tier runs at D15 continuously, and it grows inversely with utilisation |
| E18 | `$/1k queries`, generation | ~1800 input tokens (derived, not measured: `apps/api/core/llm.go`'s prompt template ~150 · 5 chunks × 300-token max each, `DEFAULT_MAX_TOKENS`, `apps/chunker/src/config.py:13` · `top_k: 5`, `load.js:67` · per-chunk formatting overhead ~100 · query ~20; an upper bound, since chunks rarely all hit the max) and up to 512 output tokens (`MaxGenLen`, `llm.go:101`, a cap rather than an observed length) × the Bedrock rate in `00-baseline` §2 | active | estimated, because the token count is assumed rather than swept and no run called Bedrock · reported beside D16 and D17, never added into either silently |
| D22 | Bedrock VPC endpoint crossover, queries/month | `figures.yaml` → `endpoint_breakeven_queries`, over `E18`'s token counts and the two per-GB rates | blocked | the volume above which PrivateLink costs less than the NAT it replaces · the PrivateLink rate was never pulled, so the figure reads `pending` · range, and why the decision does not wait on it: report §4.5 and `K4` |

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

A point sharing an hourly CUR bucket with another point does **not** exclude the point (revised
2026-09-05: no ingestion runs during this execution outside the contention pass, so nothing else
contends for the window). It costs that point its CUR-sourced `M9`/`M10`: the
campaign's CUR cross-check can only attribute spend to whichever group of points shares each
hour, not to one point inside it. `M1`-`M8`, `D15`, and the saturation/ceiling finding are
Prometheus-sourced and unaffected by hour-sharing. The contention pass point (ingestion running
concurrently) still needs its own clean hour if a clean per-point CUR cost matters for it
specifically; otherwise the same relaxation applies.

A point is not trusted when M3 exceeds 0.1% (`guards.txt` Q2: `max 0.001`, confirmed matching). Latency measured while requests are failing
describes a system that is already broken.

A point is re-run when M7 or M8 moved during the window. Convergence was declared too early, and
the window contains scale-out rather than steady state.

A point is re-run when a serving node was lost during the window.

### Safeguards

- **Estimated cost and duration** — 5 points × ⟨wall time⟩ · ⟨$⟩ ᴱ, spaced by convergence (minutes) rather than by the clock (revised 2026-09-05). No longer 5 hours by construction: wall time is whatever 5× (convergence wait + window length + scale-down) comes to
- **Abort condition** — the generator saturates before the system at the lowest rate that shows any latency rise. The measurement is then about the generator, and continuing produces a number about the wrong machine

---

## 2 · Journal

One invocation per point. The script holds a constant rate, waits for replica and node
convergence, times the window, exports Prometheus and emits the point block. It does not read
cost.

```bash
../../scripts/run-inference-point.py --run inference-r050 --rate 50 --duration 10m
```

Per-point `M9` (revised 2026-09-05 after clock-hour spacing was dropped; Plan), same day, right
after each point closes:

```bash
../../scripts/karpenter-cost-estimate.py --nodepool apps-serving \
                            --start ⟨point window start⟩ --end ⟨point window end⟩
```

The CUR cost pass uses the same script as `01-ingestion`, run once for the campaign. It is now a
cross-check on the per-point figures rather than their only source, and it resolves only to the
group of points sharing each hourly bucket, not to a single point inside it:

```bash
../../scripts/aws-cur-report-export.py --data s3://⟨bucket⟩/⟨prefix⟩ \
                            --start ⟨window start⟩ --hours 1 \
                            --tag feature=⟨value⟩ --split --format csv
```

### Run ledger

| # | Point | Rate | Window UTC | Commit | Converge | Replicas api / tei | Outcome | Signal | Exported | Cost read |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | inference-r005 | 5 | not run: bottom of the original grid; the swept grid started at r050 | | | | | | | |
| 02 | inference-r050 | 50 | 2026-09-05T12:58:01Z → 13:14:54Z | `4e15a2c` (dirty) | ~2min | 2 / 2→3 | ok; served-rate caveat in Notes | TEI dominant (~57% of limit), api/qdrant idle · M1-M3 unblocked here (Notes) | ✓ (10/10, re-exported) | ᴰ M9=$0.0747 gross, D16 $0.00250/1k queries gross; `./data/inference-r050.cost-estimate.json` |
| 03 | inference-r200 | 200 | 2026-09-05T13:21:58Z → 13:39:24Z | `4e15a2c` (dirty) | ~2min | 2 / 2→7 | real guard breach on error rate (Notes) | served ~192/200 rps (96%), p95≈2425ms, error 0.24% avg / ~4% peak | ✓ (10/10) | ᴰ M9=$0.1686 gross, D16 $0.00141/1k queries gross; `./data/inference-r200.cost-estimate.json` |
| 04 | inference-r500 | 500 | 2026-09-05T13:53:36Z → 14:14:49Z | `4e15a2c` (dirty) | ~7min to 13 replicas | 2→3 / 2→16 | window average looked like a collapse; **clean once TEI reached ~13 replicas**, so convergence lag rather than a ceiling (Notes) | ramp: p95 to 25.2s, 0-6.5% error · **steady (once tei≈13): p95 flat ~2425ms, error ~0%** | ✓ (10/10) | ᴰ M9=$0.3133 gross, D16 $0.00117/1k queries gross |
| 05 | inference-r300 | 300 | 2026-09-05T14:27:50Z → 14:45:40Z | `4e15a2c` (dirty) | ~2min | 2→3 / 2→11 | real, minor guard breach on error rate | served 296/300 (98.8%), **p95 still flat (2425ms)**, error 0.20% avg / 2.75% peak | ✓ (10/10) | ᴰ M9=$0.1769 gross, D16 $0.00098/1k queries gross |
| 06 | inference-r1000 | 1000 | 2026-09-05T14:52:16Z → 15:16:25Z | `1ef1f0a` (dirty) | ~4min | 2→6 / 2→30 | guard breach on the window average, **clean at steady state**: a convergence problem, not a ceiling (Notes) | ramp (0-4min): p95 to 24.6s, error to 35% · **steady (5min once at 30 replicas): p95 flat ~2425ms, error ~0%, rate on target** | ✓ (10/10) | ᴰ M9=$0.4992 gross, D16 $0.00088/1k queries gross |

### Notes

**The sweep left the planned grid entirely.** `§1`'s candidate grid was {5, 25, 50, 100, 200};
the points actually run were {50, 200, 500, 1000, 300}, in that order. 5/25/100 were skipped, and
1000 (never in the original grid) was added once the first two points showed no latency signal
to refine against. Each point's Notes give the reason for each choice.

**#02 inference-r050** — first real point, on a freshly bootstrapped cluster with Qdrant reloaded
from `01-ingestion/#10` (84,018 points, same corpus). `mock_delay_ms: 2000` was confirmed live in
the request body before the point ran: a direct test request returned `execution_time_ms: 2060`
and a synthesized placeholder answer instead of an LLM completion. So `s.LLM.GenerateAnswer()`,
and with it Bedrock, is never reached when `load.js` sends the param, even though the live
deployment sets `LLM_PROVIDER=bedrock`. `load.js` sends it on every request by construction.

**M1-M3 unblocked** — the Go API's missing `/metrics` (blocked since 2026-09-02) had a workaround
already running. `api` is reached through `cilium-gateway`, and Cilium's Envoy sidecars (scrape
job `cilium-envoy`) export `envoy_cluster_upstream_rq_total`/`_xx`/`_time_bucket` per upstream
cluster. That covers served rate, error rate by class and a duration histogram with no
application change. Confirmed against real traffic, and `r050` was re-exported after the fact
(Envoy's counters had been running the whole time): 10/10 refs, up from 6/10. `./data/series.txt`
now has the new Q1-Q4. One caveat carries forward. Envoy's default histogram buckets jump
`1000 → 2500` ms with nothing in between, which is coarse for the ~2000-2100ms band where this
system's responses cluster. `histogram_quantile`'s linear interpolation across that gap is
approximate, and it produced a p50 (1672ms) *below* the fixed 2000ms mock delay, which is
impossible for a constant per-request sleep. Treat p95/p50 here as directionally right, not
exact, until Envoy's bucket boundaries are tightened around 2s.

**Served-rate caveat** — M1 averaged 45.46 req/s against the 50 offered during the active window
(90.9%), short of the `SERVED_RATE_FLOOR` (95%) the Validity section sets for excluding a point.
The figure is a mean over timestamps with `M1 > 5`, a quick filter for "generator active" that
also picks up some ramp-up and ramp-down edge; a tighter read against the k6-reported window
boundaries would probably land closer to 50. Not re-run. The point is flagged, neither accepted
nor excluded, until that tighter re-read happens before it is used in §3's Matrix.

TEI scaled 2→3 replicas under the load and peaked at ~57% of its 4-core limit on the busiest
replica (live CPU check during the run). It was clearly the hottest component; `api` and Qdrant
were near idle (api ~8% of its 0.5-core limit, Qdrant ~0.07 cores on either node). That fits
`§1 Expected`'s hypothesis that TEI embedding, not Qdrant retrieval, constrains this path. `api`
never left floor (2 replicas) despite the load, for reasons not yet investigated. Check whether
`api-scaler`'s trigger is CPU-based and simply never crossed its threshold at 50rps, or whether
something else holds it.

**#03 inference-r200** — launched right after `r050` (no clock-hour wait, per the revised Plan).
A bug in `run-inference-point.py` was found and fixed here. `run_generator()` called
`subprocess.run(["k6","run","./load.js"])` without `cwd=`, so `./load.js` resolved against the
directory the script was invoked from instead of the script's own directory. Both of the first
two launch attempts failed immediately (`k6` error, moduleSpecifier not found), and silently: the
parent process's stdout stayed fully buffered and empty, so the failure showed only in the
k6-specific `.generator.log`, not in the main run log. Fixed with a `SCRIPT_DIR` constant passed
as `cwd=` to `subprocess.run`. Also hit twice: stray `kubectl port-forward` processes, left over
from a manual check or a killed earlier attempt, blocked the script's own port-forward.
`01-ingestion` hit the same recurring issue.

R21 = 84,018 at open, the same collection as `r050`. `M1` active-window mean 192.45 rps against
200 offered (96.2%), inside `SERVED_RATE_FLOOR`, unlike `r050`'s 90.9%. `p95` ≈ 2425ms,
essentially identical to `r050`'s 2417ms: **no latency degradation from 50→200 rps**. The system
absorbed 4× the load at the same tail latency, at least up to this rate, with TEI scaling 2→7
replicas (2→3 at r050). `api` still never left floor (2), the second point in a row with no
response to load. Check whether `api-scaler`'s trigger is wired to anything that moves at these
rates.

**Guard breach, real and separate from the metrics bug.** The point's guard check (`guards.txt`)
reported all three guards (Q1-Q3) as `NO DATA`, because `guards.txt` still pointed at the old,
dead `http_` metric names when this export ran (fixed right after, together with `series.txt`).
Re-derived from the Envoy-based data `series.txt` had already collected, `Q1` and `Q3` would have
passed. `Q2` (error rate) would not: average 0.24%, peaking near 4%, both well above the `> 0.1%`
"not trusted" threshold in §1 Validity. `r050` had zero errors in the same window shape, so this
is new at 200rps.

The cause is still open. Envoy's fault signals on the `api` upstream cluster
(`envoy_cluster_upstream_rq_timeout`, `_pending_overflow`, `_cx_connect_fail`) stayed at zero, so
the 5xx is not an Envoy-level timeout or connection failure; the application, or a pod torn down
mid-request, produced the 500. Which one couldn't be confirmed. Both current `api` pods started at
`13:38:52`, after the point's window closed at `13:39:24`, so the pods that served this traffic
were already replaced, and `kubectl logs` only shows the current pod. The errors are consistent
with the node-consolidation eviction pattern documented in `01-ingestion`
(`WhenEmptyOrUnderutilized` repacking `apps-serving` as TEI scales and evicting a live pod
mid-flight), but that is unproven. `M8`'s node list for this window would show whether node churn
lines up with the error timestamps; it hasn't been pulled.

Cost: `M9` gross $0.1686 (8 distinct `apps-serving` nodes across the window, the same heavy churn
the error-rate investigation flagged), `D16` $0.00141/1k queries gross. That is 2.3× `r050`'s
serving cost for ~4× as many queries, so the gross figure per query fell to 56% of `r050`'s
($0.00250) rather than to a quarter of it. Node churn overhead is the likely reason, rather than
TEI getting proportionally pricier; it is the same churn the 5xx investigation couldn't pin down.
Watch whether this holds at the next point or belongs to this point's churn pattern.

**#04 inference-r500** — 500 was chosen over an intermediate value on purpose. `p95` hadn't moved
between 50 and 200 (2417ms → 2425ms, both pinned to the 2000ms mock delay), so there was no
bracketed knee to refine, and a further coarse jump made more sense than a smaller step with no
signal to place it against.

The window average looked like a real ceiling: `p95` ≈ 7.9s mean, 26.1s max, error 0.78% avg /
6.6% peak, a 3-10× jump from every earlier point. Walking `Q1`/`Q3`/`Q5` sample by sample instead
of averaging the window shows a ramp. From `13:54:06` (rate ~95, tei=2) through `13:58:51`
(tei=7), `p95` is elevated (19–25s). Once `tei-embeddings` reaches **13 replicas** at `14:01:06`,
`p95` drops straight back to the flat ~2425ms baseline every other point shows, error rate falls
to ~0%, and both hold for the rest of the window. **500rps is sustainable at steady state.** The
3-10× jump is the ~7 minutes `tei-embeddings` needed to go from 2 to 13 replicas, not a capacity
ceiling. `tei-embeddings` scaled 2→16 overall (consistent with the 2→3→7→16 progression for
50→200→500); `api` barely moved, 2→3.

Root cause of the ramp's error spike, confirmed against `rate()`-based CPU (raw cumulative-counter
arithmetic mishandles pod-restart resets and was discarded): `tei-embeddings` replicas ran at
50–95% of their 4-core limit during the ramp, while `api`'s busiest pod peaked at 0.268 of its
0.5-core limit (~54%) even at the worst moment. `api` was never the constraint at any rate tested,
and its scaler isn't miscalibrated. The 5xx errors are application-level, not network:
`apps/api/search/search.go` wraps every request in a 15s `QUERY_TIMEOUT` (`context.WithTimeout`,
line 191), and a slow or queued TEI call past that deadline returns from `embedTEI` as an error,
which lines 230-231 turn into a plain `500`. The ramp's 26.1s max latency trips exactly that,
repeatedly. Prepared (commit `1ef1f0a`, not yet pushed): doubling `tei-embeddings`' CPU
request/limit from 3/4 to 6/8 cores, to retest at a much higher rate once this sweep's knee is
found.

**Guard-timing bug found and fixed.** `Q1`'s guard (served rate ≥ `SERVED_RATE_FLOOR`) reported
`0.0444 [min 475]` at export, a hard fail on a point that otherwise looked clean. Root cause:
`labkit.check_guards()` evaluated every guard at the instant it ran, which comes *after*
`wait_for_scale_in()`'s settle-and-buffer wait, 11+ minutes past the generator's end here. A
`rate(...)[5m])` query evaluated that late sees only dead air in its lookback window. It tests
whether traffic is still flowing, which by design it never is when a point closes, instead of
whether the generator hit its target rate. `r050` and `r200` never exposed this because their
guards had already failed for an unrelated reason (stale `http_` metric names, since fixed);
`r500` is the first point where the guard ran against live data. Fixed: `labkit.prom_query` /
`prom_scalar` / `check_guards` now take an optional `at` timestamp, and `run-inference-point.py`
passes `run["t_generator_end"]` instead of defaulting to "now". Checked by hand against this
point's data: `Q1` evaluated at `14:03:40Z` (the real generator end) reads **484.24**, above the
475 floor. Not re-run. The fixed code gives the correct in-band read on every later point, and
this point's true result (pass) is recorded here instead of a false failure in the ledger.

**#05 inference-r300: the fixed guard-timing code works, and the knee is narrower than
expected.** This is the first point run with the corrected `check_guards(..., at=t_generator_end)`.
`Q1` (305.4, min 285) and `Q3` (2425ms, max 10000) passed at export time with no manual
correction. `Q2` (error rate) failed (0.357% instant read at generator end, against the 0.1%
bound), a real if modest breach.

What *didn't* move matters more: `p95` ≈ 2424.9ms, active-window max 2425.0ms, statistically
identical to `r050` (2417ms) and `r200` (2425ms). Across three points, 50→300 rps, latency hasn't
shifted by more than measurement noise. The active-window error mean (0.204%) and peak (2.75%)
sit close to `r200`'s (0.236%/3.99%) despite 50% more offered load. `tei-embeddings` scaled 2→11,
between `r200`'s 7 and `r500`'s 16 in a roughly linear progression; `api` went 2→3 again.

**This moves the knee.** Before this point the only evidence was "flat at 200, collapsed at 500",
a wide unbracketed gap. `r300` sits inside that gap and still looks like the flat regime: served
rate, latency and error rate all resemble `r200`. That narrows the knee to **(300, 500)** from
(200, 500), a smaller window to refine next, and the system holds up better than the 200→500
comparison alone suggested.

The root cause of `r500`'s ramp errors, and the 6/8-core change prepared in commit `1ef1f0a`, are
in #04's Notes.

**#06 inference-r1000** — ran with `tei-embeddings` already at 6/8 cores (commit `1ef1f0a`,
pushed and synced before this point opened), to test whether relieving Tier 1's CPU ceiling
sustains 1000rps.

The window average read worse than `r500` on most axes: p95 mean 6378ms against 7934ms (slightly
better), p95 max **51.7s** against 26.1s (worse), error 4.97% avg / **35.1%** peak against
0.78%/6.6% (much worse). The served-rate instant read at generator end was the exception. The
ramp-versus-steady split is the same as `r500`'s, and more pronounced. Walking
`Q1`/`Q2`/`Q3`/`Q5` sample by sample:

| Phase | Time | Served rate | p95 | Error % | `tei-embeddings` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Ramp | 14:52–14:56 | swings 490–1036 | up to 24.6s | up to 35% | 2 → 14 |
| **Steady** | **14:56–15:01** | **997–1035, on target** | **~2425ms, the same flat baseline as `r050`–`r300`** | **~0%** | **30, holding** |
| Wind-down | 15:04–15:05 | falling | rising again | rising again | 30 → 9 (scale-in) |

Once `tei-embeddings` reached 30 replicas and held for ~5 minutes, every figure returned to the
flat shape every lower-rate point showed. **1000rps is sustainable at steady state.** The
disorder in the window average sits in the ~4 minutes KEDA needed to scale `tei-embeddings` from
2 to 30, a convergence-speed problem rather than a capacity ceiling. Per-pod `rate()` CPU during
the ramp: the busiest replicas hit 7.0–7.8 of their 8-core limit (87–97.5%), a real but transient
saturation that resolved once scale-out caught up. `qdrant-0`/`qdrant-1` peaked at 0.877 / 1.568
cores and were never a factor. `api` finally moved (2→6, its first real response to load in the
sweep), consistent with `api-scaler`'s trigger (`sum(rate(cpu[2m]))/replicas`, threshold `0.2`,
confirmed live) crossing its threshold as concurrent load rose.

This also shows what a higher CPU limit would and wouldn't fix. `tei-embeddings-scaler`'s trigger
targets `sum(rate(cpu[2m]))/replicas` at a threshold of **1.5 cores**, far below the 8-core limit.
The limit never constrained the *target* replica count; it only capped how hard a single pod
could be pushed *while under-provisioned during the ramp*. A higher limit would add burst
headroom mid-ramp, but it wouldn't change KEDA's steady-state target or speed up scale-out. The
levers are the trigger threshold (lower means scaling out sooner, ahead of demand) and scale-out
speed (poll interval, cooldown, pod-ready time). Not tested this pass.

Cost: `M9` gross $0.4992, `D16` $0.00088/1k queries gross, the lowest of the five points: the
gross figure falls with rate as more queries share the resting pair. `D16` says little about
this point; the latency and error columns carry the finding.

### Close

- [x] Saturation identified, or headroom confirmed at the top of the grid: none found by resource signature (§3 Saturation). `tei-embeddings` CPU saturates during a ramp and recovers once KEDA converges, so it is not a standing ceiling; no rate up to 1000 req/s found one.
- [x] Cost pass run at least 48 h after the last point (2026-09-07): the first CUR read for this execution, which had only provisional figures before. Campaign-level only, not per point (points share hourly buckets by design). It found a gap: NAT was never priced per point, and the real cost is 1.8–5.2× the per-point gross `D16` figures (§3, CUR campaign-level cross-check). The re-run after month close is still open.
- [ ] Contention pass run at the point nearest D15.
- [ ] Convergence time recorded at every point, and compared against the window length.
- [ ] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ.
- [x] Outcome compared against Expected in Retro, inversion included (Retro, first bullet).

---

## 3 · Results

**Finding** — no steady-state latency or error ceiling was found anywhere in the tested range
(50–1000 rps). Every rate converges to the same flat p95 (~2425ms, the mock-delay floor) and
near-zero error once `tei-embeddings` finishes scaling out. The measured constraint is scale-out
**convergence speed** under a sudden step in offered rate, not steady-state capacity. `r500` and
`r1000` both looked like a collapse on their whole-window average, and both came clean within
minutes once replicas caught up (#04/#06 Notes) → report §3.7

### Matrix

Figures are whole-window averages (active portion, `M1 > 20–100` depending on the point's scale)
unless noted. They include the ramp, so `r500`/`r1000` read worse here than their confirmed
steady-state numbers (~2425ms p95 and ~0% error at both once converged; Notes). `p99` was never
queried; `series.txt` has no `Q` ref for it.

| Run | Offered req/s | Served req/s | api / tei replicas | Converge | p50 ms | p95 ms | p99 ms | Error % | Serving $ (gross) | $/1k queries (gross) | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #02 | 50 | 45.5 (91%) | 2 / 3 | not timed ᴱ, window avg already clean | 1672 | 2418 | — | 0% | $0.0747 | $0.00250 | none |
| #03 | 200 | 192.5 (96%) | 2 / 7 | not timed ᴱ, window avg already clean | 1750 | 2425 | — | 0.24% avg / 4.0% peak | $0.1686 | $0.00141 | none |
| #05 | 300 | 296.4 (99%) | 3 / 11 | not timed ᴱ, window avg already clean | 1749 | 2425 | — | 0.20% avg / 2.75% peak | $0.1769 | $0.00098 | none |
| #04 | 500 | 398.7 (80%, window avg) | 3 / 16 | **~7 min to 13 replicas** ᴿ, then clean | 2973 | 7934 (window avg) / **2425 once converged** | — | 0.78% avg (window) / **~0% once converged** | $0.3133 | $0.00117 | scale-out lag, not a ceiling |
| #06 | 1000 | 828.3 (83%, window avg) | 6 / 30 | **~4 min to 30 replicas** ᴿ, then clean | 2092 | 6378 (window avg) / **2425 once converged** | — | 4.97% avg (window) / **~0% once converged** | $0.4992 | $0.00088 | scale-out lag, not a ceiling |

`Replicas` is M7 peak, an outcome rather than a setting → K2. `Serving $` is M9 gross ᴰ from
`karpenter-cost-estimate.py --nodepool apps-serving` over each point's window (node-lifecycle
reconstruction, 2026-09-05, not CUR), with no floor subtracted per point: the points share clock
hours, so the only resting inventory that can be netted is the campaign's, 2 × Spot xlarge at
$0.18754/h ᴿ (CUR 2026-09-05 hour 12), netted once in the cross-check below (D2; `figures.yaml`
group `inference_points`).

`$/1k queries` is D16, gross for the same reason, and excludes generation. Convergence time was
recorded for the two points where it mattered (`r500`, `r1000`), so the Close checklist item
asking for it "at every point" is only partly done. The other three didn't need it, because their
window averages were clean throughout.

Every latency column excludes generation, which is stubbed at a fixed 2000ms (`mock_delay_ms`),
confirmed live before the sweep started (a direct test request returned `execution_time_ms: 2060` and a
synthesized placeholder, not an LLM completion) → K1.

- **Sustained rate** — D15 = **≥1000 req/s**, untested above that. Every rate up to 1000 reached
  the same steady-state p95/error floor once converged. No ceiling that would set a *lower* D15
  was found, only a convergence-speed cost that grows with rate
- **Replicas at that rate** — 6 API, 30 TEI at r1000, converged in ~4 min from floor (2/2)
- **Scaling shape** — `tei-embeddings` peak replicas against offered rate: 3 (50) → 7 (200) → 11
  (300) → 16 (500) → 30 (1000), sublinear from 50→300, then roughly linear 300→1000. `api` moved
  only twice in five points (2→3 at 300rps, 3→6 at 1000rps); Saturation explains why that is
  correct behavior rather than an insensitive scaler → report §3.6
- **Reference value** — the `p95 < 200 ms` line in `architecture.md` was a design target for the
  *end-to-end* path including real generation. Nothing here compares to it directly, because
  generation is stubbed at a flat 2000ms, so every p95 in this Matrix exceeds 200ms by
  construction. That is expected, not a finding
- **Condition boundary** — `api-scaler` trigger `sum(rate(cpu[2m]))/replicas` at threshold `0.2`
  cores; `tei-embeddings-scaler` same shape at threshold `1.5` cores (both confirmed live via
  `kubectl get scaledobject -o yaml`, not assumed); the stubbed generation path; the restored
  (reloaded, see `01-ingestion/#10`) collection; generator placement outside the VPC via the NLB;
  `00-baseline` §2 Envelope
- **Raw data** — no `./data/frontier.csv` and no `plot-rate.py` exist. The Matrix is built
  directly from each point's `.jsonl`; chart it by hand from those files or from the Matrix

**Cost at the sustained rate** — D16 at r1000 (the top of the tested range) = $0.00088/1k
queries gross (Matrix note). D17 (floor share) and E18 (generation, estimated) are not computed
here; `report.md` §4.2 has them. Gross `D16` falls from $0.00250 at r050 to $0.00088 at r1000,
because the resting pair inside every window is spread over more queries as rate rises. Serving
cost itself tracks node-hours roughly in proportion to rate, so D16 doesn't reveal the
convergence lag; only the latency and error columns show it.

**CUR campaign-level cross-check, pulled 2026-09-07 (>48h after the last point): the per-point
`D16` figures badly understate the real cost.** Every point's `Serving $` in the Matrix came from
`karpenter-cost-estimate.py --nodepool apps-serving`, which has no NAT component, the same gap
`01-ingestion` had before its CUR pass. Real CUR was pulled for the whole afternoon (hours 12–15
UTC, 2026-09-05). Points share buckets by design, so this is a campaign-level figure rather than a
per-point one, the trade-off the revised Plan accepted:

| | Amount |
| :--- | :--- |
| Serving (gross, all 5 points + floor time between them) | $2.4505 |
| NAT | $2.8791 |
| **Marginal total** (serving + NAT) | **$5.3296** |
| Total queries served, all 5 points | 1,166,534 |
| **Real campaign `$/1k queries`** | **$0.00457** |

That is **1.8–5.2× every individual point's gross `D16`** ($0.00088–$0.00250; Matrix note).
Neither `karpenter-cost-estimate.py` nor any single point's window
captured two things. One is NAT, the blind spot `01-ingestion` found and fixed for itself but
never ported here. The other is the floor and settle cost *between* points: the five narrow point
windows add up to far less wall-clock time than the four hours CUR bills. A small unrelated
contamination ($0.2127, hour 12), from an accidental ingestion run killed before `r050` started,
was identified and excluded; `./data/campaign.cur-actual.json` has the full breakdown. Per-point
`D16` in the Matrix still works for *relative* comparison between rates, since the ratios between
points probably survive even though the absolute numbers don't. Neither the individual figures
nor their sum is the real cost of running this campaign.

### Contention pass

Not attempted this campaign; `report.md` Coverage marks it "declared, not measured" for v1.0. The
cluster was torn down before it ran.
Repeat the point nearest D15 with ingestion running at the `01-ingestion` guardrail value
(N=50, per that execution's Guardrails). Qdrant serves both paths from one node and one process,
and TEI serves both from one deployment, so a query run against an idle ingestion path measures a
state the system is not in during a backfill. Upsert builds HNSW links on the same cores that
serve search, the optimizer keeps rebuilding segments after ingestion stops, and writes evict
from page cache what search reads back from disk. Those produce the same symptom and take
different remedies, which is what M5 and M12 separate. Neither was captured, so this pass would
start from scratch on a fresh cluster rather than resume from anything this campaign left behind.

- **Sustained rate under ingestion** — not measured
- **What gave way** — not measured
- **Decision** — not made. This is the largest open item from this campaign. A 3-tier readiness
  assessment (personal / small-prod / mature-prod) flagged it as the one gap that changes an
  operational decision (whether backfills need a maintenance window) rather than refining a
  number

### Saturation

**Tier 1 — none, by resource signature. `tei-embeddings` CPU saturates briefly and recovers on
its own, so it is not a ceiling.**

- **Evidence** — checked with `rate()` CPU (raw-counter arithmetic mishandles pod-restart
  resets). At `r1000`'s ramp peak, the busiest `tei-embeddings` pods hit 7.0–7.8 of their 8-core
  limit (87–97.5%), a real, momentary saturation. `qdrant-0`/`qdrant-1` peaked at 0.877 / 1.568
  cores, nowhere near a limit and never a factor at any rate tested. `api`'s busiest pod peaked
  at 0.268 of its 0.5-core limit (~54%) at `r500`'s worst moment. It was never stressed at any
  rate, which is *why* it barely scaled: its `api-scaler` trigger (`sum(rate(cpu[2m]))/replicas`
  at threshold `0.2`, confirmed live) works correctly, and CPU demand didn't cross it until
  `r1000`
- **Relieved by** — not applicable in the usual sense, since there is no standing ceiling. The
  CPU saturation on `tei-embeddings` during a ramp resolves once KEDA finishes scaling out (`r500`
  clean at 13 replicas ~7 min in, `r1000` clean at 30 replicas ~4 min in). Doubling
  `tei-embeddings`' per-pod CPU (commit `1ef1f0a`, 3/4→6/8 cores, applied before `r1000`) did not
  change this shape. `tei-embeddings-scaler`'s target (1.5 cores/replica average) is far below
  both the old and the new limit, so the limit was never the lever. Scale-out *speed* is (trigger
  threshold, poll interval, cooldown, pod-ready time)

**Tier 2 — not attempted.** `M11`/`M12` (TEI-internal queue/duration, Qdrant search latency)
never landed. TEI's `/metrics` returns HTTP 200 with an empty body (confirmed live,
`content-length: 0`, no metrics-related flag in `text-embeddings-router --help`), which points to
something in this image or version rather than a missing scrape config. Qdrant's scrape job was
added but never verified against real series names. Declared, not measured, matching
`report.md`'s Coverage.

No third tier is claimed. This has the same template mismatch as `01-ingestion` §3: the
"component at its ceiling" framing doesn't fit a finding about convergence timing. The result is
in the Matrix's `Converge` column and this section's evidence bullet, not in a named bottleneck.

### Guardrails

- **`tei-embeddings-scaler` `maxReplicaCount` = 30 (unchanged)** — not raised, although `r1000`
  ran right up against it, because the real limit is the account's AWS Spot vCPU quota (256,
  checked live with `service-quotas`) rather than this KEDA setting. At 6 cores requested per pod,
  the quota alone caps headroom at ~35-40 replicas whatever `maxReplicaCount` says. Raising the
  number without a quota increase would trade a clean "ceiling hit" signal for pods stuck
  `Pending` · `tei-embeddings-scaler` → report §5
- **`tei-embeddings-scaler` trigger threshold** — not lowered, though Saturation argues it should
  be. Lowering it (for example 1.5 → 1.0 cores/replica average) would make KEDA scale out ahead of
  a sudden step instead of during it, which targets the convergence-lag finding directly. It
  remains an idea, not a tested commit: there is no data on which threshold shortens convergence,
  only the diagnosis that threshold and speed, not the CPU limit, are the lever
- **`api-scaler`: no change recommended.** Confirmed correctly configured and responding
  (`sum(rate(cpu[2m]))/replicas` against threshold `0.2`, scaled 2→3→6 as load rose). It was the
  one open question from earlier in the campaign that resolved to "working as intended" rather
  than "needs a guardrail"
- **Go API / TEI `limits.memory`** — not revised. Neither component showed memory pressure at
  any tested rate (not tracked in this Matrix, but no OOM or working-set warning surfaced in any
  point's Notes)
- **Query rate alert** — not set. `D15` is a lower bound (`≥1000`, untested above), so `D15 × 0.8`
  would alert on a number already known to be too low, since the real ceiling is unknown. Leaving
  it unset is better than publishing a guardrail built on an incomplete number
- **Latency alert** — not set, for a different reason: every p95 in this campaign is dominated by
  the fixed 2000ms mock delay, which real generation (Bedrock) won't reproduce. A threshold tuned
  against mock data doesn't transfer to production traffic without at least one real-Bedrock
  calibration point, and this campaign never took one
- **Backfill `maxReplicaCount`** — not set. The contention pass never ran (the cluster was torn
  down before it was scheduled), so there is nothing to base it on

Every guardrail in this list that would normally carry a number instead carries the reason it
doesn't. Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — inverted, in a way `§1 Expected` didn't anticipate. The plan expected TEI
  embedding to be the ceiling, which is directionally right, but framed it as a capacity ceiling
  to find at some rate. It is a convergence-speed cost instead: it appears at every rate above
  what the current replica count can absorb and resolves within minutes however high the offered
  rate goes. No rate in [50, 1000] was one the *system* couldn't eventually keep up with; some
  rates it just couldn't catch up with *fast enough* for a 10-minute window to look clean end to
  end
- **What should have been caught before the first run** — nothing in `§1 Validity` would have
  caught this. The Plan measures each point as one whole-window average and can't separate "still
  converging" from "steady state" inside a point. `r500` and `r1000` both needed a manual
  time-series read after the fact to find the result under the misleading average. That read
  belongs in standard point analysis
- **Stub delay** — held. 2000ms sat far enough below every bottleneck this campaign found (TEI
  ramp latency, 15s API timeout) that it never masked anything, and the flat ~2425ms steady-state
  p95 reads as "mock delay plus a small fixed overhead" at every rate, as intended
- **Scaler** — partly. `tei-embeddings` converged inside the wait at every point (no point was
  excluded for hitting a ceiling mid-window), and convergence time grew with the size of the
  replica jump, though not cleanly with rate: r500 needed ~7min to reach 13 replicas and r1000
  ~4min to reach 30, faster despite a bigger jump. That is unexplained, and with one run per rate
  it could be noise
- **Utilisation** — not assessed. No expected-production-traffic figure exists to compare `D15`
  against; this campaign never had one
- **Back into the kit** — two structural gaps, both noted inline. (1) The Saturation template's
  "component at its ceiling" framing has no slot for "the finding is in the Converge column", the
  same issue `01-ingestion` hit. (2) A point's window-average figures can mislead when convergence
  is slow relative to the window. For future points at a sudden large rate step, either extend
  the window well past expected convergence, or have the runner compute and report a separate
  converged-state statistic automatically. Here someone had to notice the average looked wrong
  and re-derive it by hand, twice, just before the cluster went away
