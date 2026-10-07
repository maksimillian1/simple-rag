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
- **Sweep order** — coarse to fine: {5, 50, 200}, then two refinement points placed around wherever p95 first approaches the target (`docs/report/methodology.md` §7). Five points total
- **Held constant** — image digests, the restored collection, Qdrant collection config, the Bedrock stub delay, both scaler triggers and thresholds, `minReplicaCount`, instance types, and every row of `00-baseline` §2 Configuration freeze
- **Not held constant, and measured instead** — API and TEI replicas, and the nodes under them. The autoscaler is the system under test → K2

Replica count is an output here, set by the scaler in response to load; at low arrival rates a
higher ceiling changes nothing because no pod is under pressure. The ceiling is raised out of
reach in `00-baseline` §2 so that it never binds, and a point that reaches it has measured the
ceiling instead of the system and is excluded.

Overload is not swept: past capacity, latency is a function of the backlog and the p95 grows with
run duration → K3.

### Unit and window

A unit is one search request, complete when the retrieved context is written to the response.

Generation is stubbed at the fixed delay frozen in `00-baseline` §2, and no run calls Bedrock
→ K1. The cost of generation is priced separately from assumed token counts in E18.

Each point runs at one constant offered rate. The design opened a point once replica stability on
both deployments, NodePool stability and a warm-up interval had each held for 60s.
`run-inference-point.py`'s `preflight()` checks less: one instant read of "replicas == floor right
now", with no duration. Either way, scaler and node convergence fall inside the point, because
both are part of what is measured. The window runs 10 min at steady rate (`--duration` default,
`run-inference-point.py:304`) and closes when the generator stops.

The load generator runs **outside the VPC**, against the internet-facing NLB in front of
`cilium-gateway` (`rag-platform`, `HTTPRoute api-route` → `api` Service). `kubectl port-forward`
tunnels to one pod and bypasses kube-proxy and the Service, so every request lands on one replica
whatever the offered concurrency: at both 50 and 1000 rps one `api` replica took 100% of traffic
while the other sat at 0 CPU. The NLB is the only path that balances across replicas the way real
traffic would.

The NLB hostname changes with every cluster recreation, so read it fresh before each run:
`kubectl get gateway cilium-gateway -n rag-platform -o
jsonpath='{.status.addresses[0].value}'` (or the underlying Service's
`.status.loadBalancer.ingress[0].hostname` if the Gateway status is unpopulated). Set it as
`api.base_url` in `scripts/env.yaml`, which exists for this kind of address (its header: `"not
frozen with any Plan and not cited by one"`), and drop `api.service`/`api.mapping` (or leave
`service` unset) so `PortForwards` doesn't open an unused tunnel.

**Points are spaced by convergence, not by the clock** (revised 2026-09-05). Between points the
generator stops and both deployments return to their minimum replicas, so each point pays its own
scale-out; that takes minutes and is the only hard spacing requirement. `01-ingestion/K6`'s
one-point-per-clock-hour rule, which let CUR attribute cost to a single point, is given up on
purpose: points may share an hourly CUR bucket, and no ingestion runs during this execution except
in the contention pass (§3), so nothing else contends for the window. Per-point cost therefore
comes from `karpenter-cost-estimate.py`'s node-lifecycle reconstruction (M9), with a
campaign-level CUR cross-check after the sweep.

### Metrics

Refs are cited from outside as `02-inference/M2`. M1 through M8 are Prometheus-sourced and gate
their point. M9 is read per point from `karpenter-cost-estimate.py` and cross-checked by a
campaign-level CUR pass at least 48 h after the last point; M10 is CUR-only and not attempted per
point. M11 and M12
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
| M10 | pod-level split of M9: api, tei, and capacity used by neither | CUR 2.0 split cost allocation columns only; `karpenter-cost-estimate.py` sees node cost, not pods | **not attempted per point** (2026-09-05) | required for the campaign, not for any point · says which of the two deployments the marginal cost went to · deferred to the campaign's CUR pass, same as `01-ingestion/M12` was declared not attempted rather than blocking · if it matters sooner, weighting each node's `M9` by its api/tei pods' CPU requests reproduces the allocation CUR's split-cost columns do; not built, and it would be new work → `01-ingestion/K5` |
| M11 | TEI inference duration and queue depth | `te_request_inference_duration` · `te_queue_size`, names unconfirmed. TEI's `/metrics` returns HTTP 200 with an empty body on this deployment (confirmed live), a deeper problem than a missing scrape config | pending ServiceMonitor, blocked on the empty-body finding | optional · separates embedding time from retrieval time inside the p95 · a queue that grows while M7 is still climbing is scaler lag, not a capacity ceiling |
| M12 | Qdrant search latency | real series names never confirmed against `:6333/metrics` | **scrape job added 2026-09-02, never applied; the cluster was torn down before a live check, so it stays unconfirmed for this campaign** | optional · an earlier read of `GET :6333/metrics` looked empty, but that check grepped for a `qdrant_`/`process_*` prefix never confirmed against the real series names, so it is inconclusive rather than proof the endpoint is disabled · scraping here doesn't use the `qdrant/qdrant` chart's `metrics.serviceMonitor` toggle (chart default `false`); this repo keeps scrapers centralized as raw `additionalScrapeConfigs` in `deploy/k8s/platform/monitoring/values/prometheus.yaml`, and a `qdrant` job already exists there (pod label `app.kubernetes.io/name=qdrant`, port `6333`) · re-check actual series names once a live cluster confirms the job resolves targets · the other half of the same split · also the second reading in the contention pass, where CPU headroom with latency rising points at page cache rather than cores |
| R13 | run log — offered rate, UTC window, config commit, stub delay, convergence time, validity decision | emitted by `run-inference-point.py` into `./data/⟨point⟩.point.md`, for 4 of the 5 real points (`r050` predates it). Each file records what only the run itself knew: the config commit and its dirty flag, the window, the generator-end instant, peak replicas, collection size at open, ceiling hits and which guards were breached. The fields fed by the metrics export and the cost pass (served rate, p95, error share, serving $) were never filled, and those numbers live in this file's Matrix and Notes instead | active; kept as the run-time record, with the generator-end instants copied into the Run ledger 2026-09-28 so nothing unique sits only here | the window is not recoverable afterwards, and the cost pass reads its windows from here |
| R14 | saturation signal — which component sat at its ceiling | read in Grafana immediately after each point · maksimillian1 | active | candidates are TEI CPU, Go API CPU, Qdrant CPU or search latency, the scaler failing to converge, or the generator itself |
| D15 | sustained rate | the highest swept rate holding p95 at the converged floor (not rising with rate), with M3 under 0.1% and M1 matching the offered rate. This criterion replaced an earlier absolute latency bound, which the 2000ms Bedrock stub makes unmeasurable: every p95 here sits on the stub's floor | active | the headline number of this execution → K3 |
| D16 | `$/1k queries`, gross | `M9 ÷ queries_served × 1000`, no floor subtracted (D2: points share clock hours, so no per-point rest inventory exists; netting happens once, at campaign level, against the 09-05 resting pair) | active, inherits M9's ᴰ until the CUR cross-check | measured, because replicas and nodes move with the axis · gross, so it carries the resting pair's share of the window and falls with rate as more queries dilute it · good for comparing rates against each other, not for pricing a query; `figures.yaml` group `inference_points` |
| D17 | floor share per 1k queries at the sustained rate | `Block B ÷ (D15 × 3600 × 730) × 1000`, Block B from `00-baseline` §2 Floor | active | the other half of what a query costs, and the larger half at low volume · a best case: it assumes the tier runs at D15 continuously, and it grows inversely with utilisation |
| E18 | `$/1k queries`, generation | ~1800 input tokens (derived, not measured: `apps/api/core/llm.go`'s prompt template ~150 · 5 chunks × 300-token max each, `DEFAULT_MAX_TOKENS`, `apps/chunker/src/config.py:13` · `top_k: 5`, `load.js:67` · per-chunk formatting overhead ~100 · query ~20; an upper bound, since chunks rarely all hit the max) and up to 512 output tokens (`MaxGenLen`, `llm.go:101`, a cap rather than an observed length) × the Bedrock rate in `00-baseline` §2 | active | estimated, because the token count is assumed rather than swept and no run called Bedrock · reported beside D16 and D17, never added into either silently |
| D22 | Bedrock VPC endpoint crossover, queries/month | `figures.yaml` → `endpoint_breakeven_queries`, over `E18`'s token counts and the two per-GB rates | active | the volume above which PrivateLink costs less than the NAT it replaces · resolves to 54,854,311<!--FD50--> ᴱ queries/month since the PrivateLink rate was pulled 2026-09-22, over token counts and a per-request overhead that are all estimates (`K4`) · why the decision does not rest on it: report §4.4 and `K4` |

If M11 and M12 never land, the constraint is named at component granularity from M4 and M5, and
the embedding-versus-retrieval split goes to report Coverage.

### Validity

A point is excluded when:

- the served rate on M1 falls short of the offered rate by more than a few percent: the generator was the limit → K3
- M7 reaches `maxReplicaCount` on either deployment: the point describes a configured limit
- the collection differs from the restored snapshot, the stub delay differs from the frozen value, or either scaler trigger or threshold changed: each changes what the p95 describes

A point is not trusted when M3 exceeds 0.1% (`guards.txt` Q2: `max 0.001`, confirmed matching);
latency measured while requests fail describes a system already broken.

A point is re-run when M7 or M8 moved during the window (convergence was declared too early and
the window holds scale-out), or when a serving node was lost during the window.

Sharing an hourly CUR bucket with another point does not exclude a point (revised 2026-09-05,
Plan). It costs the point its CUR-sourced `M9`/`M10`, because the campaign's CUR pass can
attribute spend only to the group of points sharing each hour. `M1`-`M8`, `D15` and the
saturation finding are Prometheus-sourced and unaffected. The contention pass point still needs
its own clean hour if a per-point CUR cost matters for it.

### Safeguards

- **Estimated cost and duration** — 5 points × ⟨wall time⟩ · ⟨$⟩ ᴱ, spaced by convergence (revised 2026-09-05), so wall time is 5× (convergence wait + window length + scale-down) and not 5 hours
- **Abort condition** — the generator saturates before the system at the lowest rate that shows any latency rise. The measurement is then about the generator, and continuing produces a number about the wrong machine

---

## 2 · Journal

One invocation per point. The script holds a constant rate, waits for replica and node
convergence, times the window, exports Prometheus and emits the point block. It does not read
cost.

```bash
../../scripts/run-inference-point.py --run inference-r050 --rate 50 --duration 10m
```

Per-point `M9`, same day, right after each point closes:

```bash
../../scripts/karpenter-cost-estimate.py --nodepool apps-serving \
                            --start ⟨point window start⟩ --end ⟨point window end⟩
```

The CUR cost pass uses the same script as `01-ingestion`, run once for the campaign. It
cross-checks the per-point figures and resolves only to the group of points sharing each hourly
bucket:

```bash
../../scripts/aws-cur-report-export.py --data s3://⟨bucket⟩/⟨prefix⟩ \
                            --start ⟨window start⟩ --hours 1 \
                            --tag feature=⟨value⟩ --split --format csv
```

### Run ledger

A point's `Generator ended` is the instant its offered-rate guard must be read at, and it can't be recovered once the cluster is gone: a `rate()` query read later sees dead air and fails a point that passed, as happened to `r500` (Notes). Copied here from `./data/<point>.point.md` on 2026-09-28 so the ledger stands alone; `r050` predates the field.

| # | Point | Rate | Window UTC | Generator ended | Commit | Converge | Replicas api / tei | Outcome | Signal | Exported | Cost read |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | inference-r005 | 5 |  | not run: bottom of the original grid; the swept grid started at r050 | | | | | | | |
| 02 | inference-r050 | 50 | 2026-09-05T12:58:01Z → 13:14:54Z | not recorded | `4e15a2c` (dirty) | ~2min | 2 / 2→3 | ok; served-rate caveat in Notes | TEI dominant (~57% of limit), api/qdrant idle · M1-M3 unblocked here (Notes) | ✓ (10/10, re-exported) | ᴰ M9=$0.0747<!--FM31--> gross, D16 $0.00250<!--FD78-->/1k queries gross; `./data/inference-r050.cost-estimate.json` |
| 03 | inference-r200 | 200 | 2026-09-05T13:21:58Z → 13:39:24Z | 13:32:11Z | `4e15a2c` (dirty) | ~2min | 2 / 2→7 | real guard breach on error rate (Notes) | served ~192/200 rps (96%), p95≈2425ms, error 0.24% avg / ~4% peak | ✓ (10/10) | ᴰ M9=$0.1686<!--FM33--> gross, D16 $0.00141<!--FD79-->/1k queries gross; `./data/inference-r200.cost-estimate.json` |
| 04 | inference-r500 | 500 | 2026-09-05T13:53:36Z → 14:14:49Z | 14:03:40Z | `4e15a2c` (dirty) | ~7min to 13 replicas | 2→3 / 2→16 | window average looked like a collapse; **clean once TEI reached ~13 replicas**, so convergence lag rather than a ceiling (Notes) | ramp: p95 to 25.2s, 0-6.5% error · **steady (once tei≈13): p95 flat ~2425ms, error ~0%** | ✓ (10/10) | ᴰ M9=$0.3255<!--FM37--> gross, D16 $0.00121<!--FD81-->/1k queries gross |
| 05 | inference-r300 | 300 | 2026-09-05T14:27:50Z → 14:45:40Z | 14:37:53Z | `4e15a2c` (dirty) | ~2min | 2→3 / 2→11 | real, minor guard breach on error rate | served 296/300 (98.8%), **p95 still flat (2425ms)**, error 0.20% avg / 2.75% peak | ✓ (10/10) | ᴰ M9=$0.1769<!--FM35--> gross, D16 $0.00098<!--FD80-->/1k queries gross |
| 06 | inference-r1000 | 1000 | 2026-09-05T14:52:16Z → 15:16:25Z | 15:05:34Z | `1ef1f0a` (dirty; **TEI 6/8**) | ~4min | 2→6 / 2→30 | guard breach on the window average, **clean at steady state**: a convergence problem, not a ceiling (Notes) | ramp (0-4min): p95 to 24.6s, error to 35% · **steady (5min once at 30 replicas): p95 flat ~2425ms, error ~0%, rate on target** | ✓ (10/10) | ᴰ M9=$0.4992<!--FM39--> gross, D16 $0.00088<!--FD82-->/1k queries gross |

### Notes

**The sweep left the planned grid.** `§1` planned {5, 25, 50, 100, 200}; the points run were
{50, 200, 500, 1000, 300}, in that order. 5, 25 and 100 were skipped, and 1000, never in the grid,
was added once the first two points showed no latency signal to refine against. Each point's
Notes give its reason.

**#02 inference-r050** — first real point, on a freshly bootstrapped cluster with Qdrant reloaded
from `01-ingestion/#10` (84,018 points, same corpus). `mock_delay_ms: 2000` was confirmed live
before the point ran: a direct test request returned `execution_time_ms: 2060` and a synthesized
placeholder answer instead of an LLM completion. `load.js` sends the param on every request, so
`s.LLM.GenerateAnswer()`, and Bedrock with it, is never reached, although the deployment sets
`LLM_PROVIDER=bedrock`.

**M1-M3 unblocked** — the Go API has had no `/metrics` since 2026-09-02, but `api` is reached
through `cilium-gateway`, and Cilium's Envoy sidecars (scrape job `cilium-envoy`) already export
`envoy_cluster_upstream_rq_total`/`_xx`/`_time_bucket` per upstream cluster: served rate, error
rate by class and a duration histogram, with no application change. Confirmed against real
traffic. Envoy's counters had run the whole time, so `r050` was re-exported after the fact: 10/10
refs, up from 6/10, with the new Q1-Q4 in `./data/series.txt`. One caveat carries forward:
Envoy's default buckets jump `1000 → 2500` ms, coarse for the ~2000-2100ms band where responses
cluster. `histogram_quantile`'s linear interpolation across that gap produced a p50 of 1672ms,
*below* the fixed 2000ms mock delay, which a constant per-request sleep makes impossible. Read
p95/p50 here as directionally right but not exact until the buckets are tightened around 2s.

**Served-rate caveat** — M1 averaged 45.46 req/s against 50 offered over the active window
(90.9%), below the 95% `SERVED_RATE_FLOOR` at which Validity excludes a point. The mean is over
timestamps with `M1 > 5`, a quick "generator active" filter that also catches some ramp edge; a
read against the k6-reported window boundaries would probably land closer to 50. Not re-run. The
point is flagged, neither accepted nor excluded, until that tighter re-read happens before it is
used in §3's Matrix.

TEI scaled 2→3, and its busiest replica peaked at ~57% of its 4-core limit (live CPU check).
`api` (~8% of its 0.5-core limit) and Qdrant (~0.07 cores per node) were near idle, which fits
`§1 Expected`: TEI embedding, not Qdrant retrieval, constrains this path. `api` never left its
floor of 2 replicas; whether `api-scaler`'s CPU trigger simply never crossed its threshold at
50rps was left open here.

**#03 inference-r200** — launched right after `r050`, with no clock-hour wait. A bug in
`run-inference-point.py` surfaced here: `run_generator()` called
`subprocess.run(["k6","run","./load.js"])` without `cwd=`, so `./load.js` resolved against the
caller's directory. The first two launch attempts failed at once (`k6` error, moduleSpecifier not
found) and silently, because the parent's stdout stayed buffered and empty and the error reached
only the k6 `.generator.log`. Fixed with a `SCRIPT_DIR` constant passed as `cwd=`. Twice more,
stray `kubectl port-forward` processes left over from a manual check or a killed attempt blocked
the script's own port-forward, the same recurring issue `01-ingestion` hit.

R21 = 84,018 at open, the same collection as `r050`. `M1`'s active-window mean was 192.45 rps
against 200 offered (96.2%), inside `SERVED_RATE_FLOOR`. `p95` ≈ 2425ms against `r050`'s 2417ms:
4× the load at the same tail latency, with TEI scaling 2→7 replicas (2→3 at r050). `api` stayed
at 2 for the second point running.

**Guard breach, real and separate from the metrics bug.** The guard check reported Q1-Q3 as
`NO DATA`, because `guards.txt` still pointed at the dead `http_` metric names when this export
ran (fixed right after, with `series.txt`). Re-derived from the Envoy data `series.txt` had
already collected, `Q1` and `Q3` pass and `Q2` (error rate) fails: 0.24% average, peaking near
4%, against the 0.1% "not trusted" threshold. `r050` had zero errors in the same window shape, so
the errors are new at 200rps.

The cause is still open. Envoy's fault counters on the `api` upstream
(`envoy_cluster_upstream_rq_timeout`, `_pending_overflow`, `_cx_connect_fail`) stayed at zero, so
the 500s came from the application or from a pod torn down mid-request. Which one can't be
confirmed: both current `api` pods started at `13:38:52`, after the point's window closed at
`13:39:24`, so the pods that served the traffic were gone and `kubectl logs` shows only the
current pod. The errors fit the node-consolidation eviction pattern from `01-ingestion`
(`WhenEmptyOrUnderutilized` repacking `apps-serving` as TEI scales and evicting a live pod
mid-flight), but that is unproven; `M8`'s node list for the window would show whether node churn
lines up with the error timestamps, and it hasn't been pulled.

Cost: `M9` gross $0.1686<!--FM33--> over 8 distinct `apps-serving` nodes, the same heavy churn,
and `D16` $0.00141<!--FD79-->/1k queries gross. That is 2.3× `r050`'s serving cost for ~4× the
queries, so gross cost per query fell to 56% of `r050`'s ($0.00250<!--FD78-->) rather than to a
quarter. Node churn is the likely reason, rather than TEI getting pricier per query.

**#04 inference-r500** — `p95` hadn't moved between 50 and 200 (2417ms → 2425ms, both pinned to
the 2000ms mock delay), so there was no knee to refine, and a coarse jump to 500 made more sense
than a small step with nothing to place it against.

The window average looked like a ceiling: `p95` ≈ 7.9s mean, 26.1s max, error 0.78% avg / 6.6%
peak, 3-10× every earlier point. Read sample by sample (`Q1`/`Q3`/`Q5`), it is a ramp. From
`13:54:06` (rate ~95, tei=2) through `13:58:51` (tei=7), `p95` sits at 19–25s. Once
`tei-embeddings` reaches **13 replicas** at `14:00:51`, `p95` drops back to the flat ~2425ms every
other point shows and the point holds 499<!--FM66-->–501<!--FM67--> req/s for a minute, to
`14:01:51`. **500rps is reachable at steady state**; the 3-10× jump is the ~7 minutes
`tei-embeddings` took to go from 2 to 13 replicas. It is thinner than it first read, though:
errors over that minute are 0.25<!--FM68-->%, above `D15`'s 0.1<!--FR29-->% bound, and only the
two samples at `14:00:51` and `14:01:06` sit under it. From `14:02:06` served falls to 345–455
req/s at an unchanged offered rate while the VU pool is only ~1,050 of 2,500 in use — so these
are not dropped iterations, and they are absent from the upstream counter rather than answered
with a 5xx, which points at connection-level failures ahead of the cluster. Unexplained; the
cluster is gone. Across the whole phase, `14:00:51`-`14:03:36`, the point served
457<!--FM69--> req/s at 0.49<!--FM70-->%. It scaled 2→16 overall (2→3→7→16 for 50→200→500); `api` went 2→3.

Root cause of the ramp's errors, confirmed with `rate()`-based CPU (raw cumulative-counter
arithmetic mishandles pod-restart resets and was discarded): `tei-embeddings` replicas ran at
50–95% of their 4-core limit during the ramp, while `api`'s busiest pod peaked at 0.268 of its
0.5-core limit (~54%) at the worst moment. `api` was never the constraint at any tested rate, and
its scaler isn't miscalibrated. The 5xx are application-level: `apps/api/search/search.go` wraps
every request in a 15s `QUERY_TIMEOUT` (`context.WithTimeout`, line 191), and a TEI call slow or
queued past that deadline returns from `embedTEI` as an error, which lines 230-231 turn into a
plain `500`. The ramp's 26.1s max latency trips it repeatedly. Prepared in commit `1ef1f0a` (not
yet pushed): `tei-embeddings`' CPU request/limit doubled from 3/4 to 6/8 cores, to retest at a
much higher rate once the knee is found.

**Guard-timing bug found and fixed.** `Q1` (served rate ≥ `SERVED_RATE_FLOOR`) read
`0.0444 [min 475]` at export, a hard fail on a point that otherwise looked clean.
`labkit.check_guards()` evaluated every guard at the instant it ran, after `wait_for_scale_in()`'s
settle-and-buffer wait, here 11+ minutes past the generator's end, so the `rate(...)[5m])` query
saw only dead air: it tested whether traffic was still flowing, which it never is when a point
closes. `r050` and `r200` hid this because their guards had already failed on the stale `http_`
names; `r500` is the first point whose guard ran against live data. `labkit.prom_query` /
`prom_scalar` / `check_guards` now take an optional `at` timestamp, and `run-inference-point.py`
passes `run["t_generator_end"]`. Read by hand at `14:03:40Z`, the real generator end, `Q1` is
**484.24**, above the 475 floor. Not re-run: later points get the in-band read from the fixed
code, and this point's true result (pass) is recorded here in place of the false failure.

**#05 inference-r300** — the first point run with `check_guards(..., at=t_generator_end)`. `Q1`
(305.4, min 285) and `Q3` (2425ms, max 10000) passed at export with no manual correction. `Q2`
failed: 0.357% at generator end against the 0.1% bound, a real if modest breach.

Latency didn't move: `p95` ≈ 2424.9ms, active-window max 2425.0ms, the same as `r050` (2417ms) and
`r200` (2425ms) within measurement noise across 50→300 rps. The active-window error mean (0.204%)
and peak (2.75%) are close to `r200`'s (0.236%/3.99%) at 50% more load. `tei-embeddings` scaled
2→11, between `r200`'s 7 and `r500`'s 16; `api` went 2→3 again.

This narrows the knee from (200, 500) to **(300, 500)**: the only evidence before it was "flat at
200, collapsed at 500", and `r300` still looks like the flat regime on served rate, latency and
error rate. `r500`'s root cause and the 6/8-core change are in #04's Notes.

**#06 inference-r1000** — ran with `tei-embeddings` already at 6/8 cores (commit `1ef1f0a`,
pushed and synced before the point opened), to test whether relieving Tier 1's CPU ceiling
sustains 1000rps.

On the window average it read worse than `r500` on most axes: p95 mean 6378ms against 7934ms
(slightly better), p95 max **51.7s** against 26.1s, error 4.97% avg / **35.1%** peak against
0.78%/6.6%; the served-rate instant read at generator end was the exception. Read sample by
sample (`Q1`/`Q2`/`Q3`/`Q5`), it splits into ramp and steady state like `r500`, more sharply:

| Phase | Time | Served rate | p95 | Error % | `tei-embeddings` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Ramp | 14:52–14:57 | swings 490–1036 | up to 24.6s | up to 35% | 2 → 17 |
| **Hold** | **14:57:16–14:59:01** | **998<!--FM60-->–1,001<!--FM61-->, on target** | **~2425ms, the same flat baseline as `r050`–`r300`** | **0.02<!--FM62-->%** | **30, holding** |
| Excursion | 14:59:16–15:00:01 | 760–885 | 2427–2429ms | ~1.2% | 30, holding |
| Recovered | 15:00:16–15:01:01 | 980–997 | ~2427ms | 0.18% → 0 | 30, holding |
| Generator stall | 15:01:16–15:03:31 | 563 → 445 → 0 | no requests to measure | — | 30 → 10 (scale-in, no traffic) |
| Second ramp | 15:03:46–15:06:01 | 17 → 901, falling again | **to 51.7s** | to 8.9% | 6 → 27 |

Once `tei-embeddings` reached 30 replicas at `14:57:16`, every figure returned to the flat shape
of the lower-rate points and stayed there for 1m45s. **1000rps is reachable at steady state**;
the disorder in the average is the ~4 minutes KEDA needed to scale `tei-embeddings` from 2 to 30.
Two corrections to the earlier read of this point. The hold is 1m45s, not five minutes: 30
replicas were reached at `14:57:16`, not at 14:56, and a 45-second excursion at `14:59:16` drops
served to 760–885 req/s at ~1.2% errors with the replica count unchanged — so the phase as a
whole is 955<!--FM63--> req/s at 0.28<!--FM64-->%, against `D15`'s 0.1<!--FR29-->% bound. And the
"wind-down" is the **generator**, not scale-in: served falls off a cliff at `15:01:16` and reads
zero for ~105s while `k6` is still scheduling, k6's own progress output stops between `08m30.9s`
and `11m28.1s` elapsed with completions at 43/s over those 178s and its VU count climbing from
~2,100 to 4,252, and `tei-embeddings` scales 30 → 6 for want of traffic. The second ramp after it
is where this point's worst readings come from — p95 51.7s at `15:06:01` and the 59/s error peak
— and they belong to the generator's recovery, not to the system under load. During the ramp
the busiest replicas hit 7.0–7.8 of their 8-core limit (87–97.5%, per-pod `rate()` CPU), a real
saturation that cleared once scale-out caught up. `qdrant-0`/`qdrant-1` peaked at 0.877 / 1.568
cores and were never a factor. `api` finally moved, 2→6, its first response to load in the sweep,
as `api-scaler`'s trigger (`sum(rate(cpu[2m]))/replicas`, threshold `0.2`, confirmed live)
crossed its threshold.

A higher CPU limit fixes less than it seems. `tei-embeddings-scaler` targets
`sum(rate(cpu[2m]))/replicas` at **1.5 cores**, far below the 8-core limit, so the limit never set
the *target* replica count; it only capped how hard one pod could be pushed while the deployment
was under-provisioned. It adds burst headroom mid-ramp and changes neither KEDA's steady-state
target nor scale-out speed. The levers are the trigger threshold (lower scales out sooner, ahead
of demand) and scale-out speed (poll interval, cooldown, pod-ready time); neither was tested.

Cost: `M9` gross $0.4992<!--FM39-->, `D16` $0.00088<!--FD82-->/1k queries gross, the lowest of the
five, because gross cost falls with rate as more queries share the resting pair. This point's
finding is in the latency and error columns, not in `D16`.

### Close

- [x] Saturation identified, or headroom confirmed at the top of the grid: none found by resource signature (§3 Saturation). `tei-embeddings` CPU saturates during a ramp and recovers once KEDA converges, so it is not a standing ceiling; no rate up to 1000 req/s found one.
- [x] Cost pass run at least 48 h after the last point (2026-09-07): the first CUR read for this execution, which had only provisional figures before. Campaign-level only, not per point (points share hourly buckets by design). It found a gap: NAT was never priced per point, and the real cost is 1.5–4.3× the per-point gross `D16` figures (§3, CUR campaign-level cross-check). The re-run after month close is still open.
- [ ] Contention pass run at the point nearest D15.
- [ ] Convergence time recorded at every point, and compared against the window length.
- [x] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ. Done 2026-09-21; each one also carries its `figures.yaml` ref, so the value is checked and not merely marked.
- [x] Outcome compared against Expected in Retro, inversion included (Retro, first bullet).

---

## 3 · Results

**Finding** — no steady-state latency or error ceiling was found anywhere in the tested range
(50–1000 rps). Every rate converges to the same flat p95 (~2425ms, the mock-delay floor) once
`tei-embeddings` finishes scaling out. The measured constraint is scale-out **convergence speed**
under a sudden step in offered rate, not steady-state capacity. `r500` and `r1000` both looked
like a collapse on their whole-window average, and both came clean once replicas caught up
(#04/#06 Notes) → report §3.7

**How long "clean" lasted, re-read 2026-10-03.** Sample by sample, each of the two points holds
its offered rate at the p95 floor for about a minute and a half, and the phase around that hold
does not meet `D15`'s 0.1<!--FR29-->% error bound. `r1000`: 998<!--FM60-->–1,001<!--FM61--> req/s
from 14:57:16 to 14:59:01Z at 0.02<!--FM62-->% errors, then 955<!--FM63--> req/s at
0.28<!--FM64-->% across the whole phase to 15:01:01Z. `r500`: 499<!--FM66-->–501<!--FM67--> req/s
from 14:00:51 to 14:01:51Z, but already at 0.25<!--FM68-->% errors, and 457<!--FM69--> req/s at
0.49<!--FM70-->% across its phase to 14:03:36Z. Both phases end on the generator rather than on
the system, and the earlier "~0% once converged" reading was the hold's shape generalised to the
phase. The generator's own share is in the Matrix note below.

### Matrix

Figures are whole-window averages (active portion, `M1 > 20–100` depending on the point's scale)
unless noted. They include the ramp, so `r500`/`r1000` read worse here than the hold each one
reached (Finding, above; Notes). `p99` was never queried at either instrument.

**Why two p95 columns, added 2026-10-04.** Envoy answers over any window asked for, but its
buckets jump 1000 → 2500ms and every response in this campaign lands inside that one bucket, so
`histogram_quantile` interpolates: `1000 + 0.95 × 1500 = 2425`. That is the printed figure —
arithmetic, not measurement — which is why four rates share it to the millisecond, and
`1000 + 0.5 × 1500` is why p50 reads 1672ms, below the 2000ms stub every request pays (M2 already
flagged that as impossible). k6 times each request exactly, from outside the VPC, so it carries
the internet hop and the NLB on top and ought to read higher; it reads 300-400ms lower instead,
which is the size of Envoy's overstatement. k6's own limit is the window: its summary covers a
whole run, so `r500` and `r1000` carry their scale-out minutes in that column and the hold cannot
be cut out of it — per-request output (`--out json`) was never captured and the cluster is gone.
For those two rows Envoy's converged figure is the one to read, with the overstatement understood.

They also include what the **generator** failed to send. k6 schedules by the clock but needs a
free VU per iteration, and `load.js` sizes the pool off the stub (rate × 2.5s, doubled). The ramp
pushed p95 to 25s, demand for slots past the cap, and k6 dropped what it could not start:
32,045<!--FM71--> of 300,000 scheduled at `r500` (10.7<!--FD145-->%, the pool pinned at
2,500<!--FR31--> VUs from 00m11.9s) and 30,985<!--FM65--> of 600,000 at `r1000`
(5.2<!--FD144-->%, pool 5,000<!--FR30-->). This execution reads served rate from Prometheus and
never from k6's own output (M1), which is right for the system's view and left the one
generator-side instrument unread until 2026-10-03.

| Run | Offered req/s | Served req/s | api / tei replicas | Converge | p50 ms ᴿ | p95 ms ᴿ (Envoy) | p95 ms (k6) | Error % | Queries served | Serving $ (gross) | $/1k queries (gross) | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| #02 | 50 | 45.5 (91%) | 2 / 3 | not timed ᴱ, window avg already clean | 1672 | 2418 | **2040** | 0% | 29,938<!--FM32--> | $0.0747<!--FM31--> | $0.00250<!--FD78--> | none |
| #03 | 200 | 192.5 (96%) | 2 / 7 | not timed ᴱ, window avg already clean | 1750 | 2425 | **2150** | 0.24% avg / 4.0% peak | 119,623<!--FM34--> | $0.1686<!--FM33--> | $0.00141<!--FD79--> | none |
| #05 | 300 | 296.4 (99%) | 3 / 11 | not timed ᴱ, window avg already clean | 1749 | 2425 | **2060** | 0.20% avg / 2.75% peak | 180,001<!--FM36--> | $0.1769<!--FM35--> | $0.00098<!--FD80--> | none |
| #04 | 500 | 398.7 (80%, window avg) · **499<!--FM66-->–501<!--FM67--> held 1 min** | 3 / 16 | **~7 min to 13 replicas** ᴿ, then clean | 2973 | 7934 (window avg) / **2425 once converged** | 10,630 (whole run) | 0.78% avg (window) / 0.49<!--FM70-->% steady phase | 267,956<!--FM38--> | $0.3255<!--FM37--> | $0.00121<!--FD81--> | scale-out lag, not a ceiling |
| #06 | 1000 | 828.3 (83%, window avg) · **998<!--FM60-->–1,001<!--FM61--> held 1m45s** | 6 / 30 | **~4 min to 30 replicas** ᴿ, then clean | 2092 | 6378 (window avg) / **2425 once converged** | 4,730 (whole run) | 4.97% avg (window) / 0.28<!--FM64-->% steady phase, 0.02<!--FM62-->% in the hold | 568,923<!--FM40--> | $0.4992<!--FM39--> | $0.00088<!--FD82--> | scale-out lag, not a ceiling |

**#06 is not the same configuration as the others.** `r1000` ran `tei-embeddings` at `cpu 6 / 8`
(commit `1ef1f0a`, applied just before it); #01-#05 ran the frozen `3 / 4` (`00-baseline` §2
Configuration freeze). For the latency and scaling columns the change left the shape alone,
because the scaler's target sits far below either limit (Saturation). Its effect on the two cost
columns is unmeasured: a 6-core request fits fewer pods per node, and #06 is the one point whose
node mix is dominated by `4xlarge` (5 of 11 seen, against 12 of 17 at `xlarge` for #04), but
`karpenter-cost-estimate.py` reconstructs node lifecycles rather than concurrency, so neither
direction nor magnitude can be read off it. Declared the same way as D2's instance-selection
caveat.

`Replicas` is M7 peak, an outcome → K2. `Serving $` is M9 gross ᴰ from
`karpenter-cost-estimate.py --nodepool apps-serving` over each point's window (node-lifecycle
reconstruction, 2026-09-05, not CUR). No floor is subtracted per point, because the points share
clock hours; the only resting inventory that can be netted is the campaign's, 2 × Spot xlarge at
$0.18754<!--FD58-->/h ᴰ (CUR 2026-09-05 hour 12), netted once in the cross-check below (D2;
`figures.yaml` group `inference_points`). `$/1k queries` is D16, gross for the same reason, and
excludes generation.

Convergence time was recorded only for `r500` and `r1000`, the two points whose window averages
weren't clean, so the Close item asking for it at every point is partly done. Latency columns
exclude generation, stubbed at a fixed 2000ms (`mock_delay_ms`, confirmed live, #02 Notes) → K1.

- **Sustained rate** — D15 = **≥1000 req/s**, untested above that. Every rate up to 1000 reached
  the same steady-state p95 and error floor once converged; what grows with rate is convergence
  time, which sets no lower D15
- **Replicas at that rate** — 6 API, 30 TEI at r1000, converged in ~4 min from floor (2/2)
- **Scaling shape** — `tei-embeddings` peak replicas against offered rate: 3 (50) → 7 (200) → 11
  (300) → 16 (500) → 30 (1000), sublinear from 50→300, then roughly linear 300→1000. `api` moved
  only twice in five points (2→3 at 300rps, 3→6 at 1000rps); Saturation explains why that is the
  scaler working as configured → report §3.6
- **Reference value** — none for this campaign.
- **Condition boundary** — `api-scaler` trigger `sum(rate(cpu[2m]))/replicas` at threshold `0.2`
  cores; `tei-embeddings-scaler` same shape at threshold `1.5` cores (both confirmed live via
  `kubectl get scaledobject -o yaml`); the stubbed generation path; the restored
  (reloaded, see `01-ingestion/#10`) collection; generator placement outside the VPC via the NLB;
  `00-baseline` §2 Envelope
- **Raw data** — `./data/⟨point⟩.jsonl`, `⟨point⟩.cost-estimate.json`,
  `⟨point⟩.meta.json`, `⟨point⟩.point.md` and `⟨point⟩.generator.log` per point, plus
  `series.txt`. The Matrix is built directly from them

**Cost at the sustained rate** — D16 at r1000, the top of the tested range, is
$0.00088<!--FD82-->/1k queries gross. D17 (floor share) and E18 (generation, estimated) are in
`report.md` §4.2. Gross `D16` falls from $0.00250<!--FD78--> at r050 to $0.00088<!--FD82--> at
r1000 because the resting pair inside every window is spread over more queries. Serving cost
tracks node-hours roughly in proportion to rate, so D16 hides the convergence lag that the
latency and error columns show.

**CUR campaign-level cross-check, pulled 2026-09-07 (>48h after the last point): the per-point
`D16` figures badly understate the real cost.** `Serving $` in the Matrix comes from
`karpenter-cost-estimate.py --nodepool apps-serving`, which has no NAT component, the gap
`01-ingestion` had before its CUR pass. CUR was pulled for the whole afternoon (hours 12–15 UTC,
2026-09-05); points share buckets by design, so the figure is campaign-level, as the revised Plan
accepted:

| | Amount |
| :--- | :--- |
| Serving, gross: all 5 points plus the floor time between them | $2.4505<!--FD60--> ᴰ |
| NAT: bytes $2.3610<!--FM18--> + hourly $0.2080<!--FM19--> + regional transfer $0.3093<!--FM20--> | $2.8783<!--FD61--> ᴰ |
| **Gross total** | **$5.3288<!--FD89--> ᴰ** |
| less the floor, netted once here: the 09-05 resting pair across the 4<!--FR22--> campaign hours at $0.18754<!--FD58-->/h ᴰ, plus the NAT hourly fee | −$0.9582<!--FD62--> ᴰ |
| **Marginal total** | **$4.3706<!--FD63--> ᴰ** |
| Total queries served, all 5 points | 1,166,441<!--FD59--> ᴰ |
| **Real campaign `$/1k queries`** | **$0.00375<!--FD65--> ᴰ** |

**What a query is counted as.** Each point counts `http_reqs` from its own k6 summary: requests
the system answered, error responses included, one request per iteration. k6 also reports
*interrupted* iterations, still running when the test ended and its graceful-stop window expired:
7 at r050 and 93 at r1000, none elsewhere. They are excluded and are not in `http_reqs` either,
since k6 recorded no response for them and the log doesn't say whether the request had left the
client. The server side can't settle it: Envoy's rate integrated over each window lands 5–6% from
the client's count, hundreds to tens of thousands of requests, far too coarse for 7. At 0.02% of
a point the choice moves nothing the report prints; it is fixed one way so the five points count
the same thing and a row's queries, error rate and `$/1k` share one denominator. *Dropped*
iterations are not counted at all: the scheduler never started them for want of a free VU (56 at
r050, 30,985 at r1000), which is the generator's own ceiling, and no request left for them.

The floor comes out once, here, against the inventory that day actually rested on (D2); the
points share clock hours, so none has a resting hour of its own to subtract. The gross total is
what CUR billed, and the marginal is what an additional query cost once the tier was standing.

That campaign figure is **1.5<!--FD90-->–4.3<!--FD91-->× every point's gross `D16`**
($0.00088<!--FD82-->–$0.00250<!--FD78-->). The per-point windows missed two things: NAT, the blind
spot `01-ingestion` fixed for itself and never ported here, and the floor and settle cost
*between* points, since the five windows add up to far less wall time than the four hours CUR
bills. A small unrelated contamination ($0.2127<!--FM41-->, hour 12), from an accidental
ingestion run killed before `r050` started, was identified and excluded. Each component's CUR
slice is named in `figures.yaml` group `campaign_0905`. Per-point `D16` still serves for comparing
rates, since the ratios between points probably survive, but neither the individual figures nor
their sum is the cost of running this campaign.

### Contention pass

Not attempted: the cluster was torn down before it ran, and `report.md` Coverage marks it
"declared, not measured" for v1.0. The plan was to repeat the point nearest D15 with ingestion
running at the `01-ingestion` guardrail value (N=50, per that execution's Guardrails). Qdrant
serves both paths from one node and one process, and TEI from one deployment, so a query run
against an idle ingestion path measures a state the system is not in during a backfill. Upsert
builds HNSW links on the cores that serve search, the optimizer keeps rebuilding segments after
ingestion stops, and writes evict from page cache what search reads back from disk. Those give the
same symptom and need different remedies, which M5 and M12 would separate. Neither was captured,
so the pass would start from scratch on a fresh cluster.

- **Sustained rate under ingestion** — not measured
- **What gave way** — not measured
- **Decision** — not made. This is the largest open item from this campaign: a 3-tier readiness
  assessment (personal / small-prod / mature-prod) flagged it as the one gap that changes an
  operational decision, whether backfills need a maintenance window

### Saturation

**Tier 1: none by resource signature. `tei-embeddings` CPU saturates briefly and recovers on its
own.**

- **Evidence** — `rate()` CPU (raw-counter arithmetic mishandles pod-restart resets). At
  `r1000`'s ramp peak the busiest `tei-embeddings` pods hit 7.0–7.8 of their 8-core limit
  (87–97.5%), a real, momentary saturation. `qdrant-0`/`qdrant-1` peaked at 0.877 / 1.568<!--FM59-->
  cores against a 2<!--FR27-->-core limit (`qdrant-values.yaml`), so the busier replica reached
  78<!--FD137-->% of its ceiling at `r1000` and far less below it. That is no constraint in this
  sweep, but Qdrant is the one component whose headroom the top of the range consumed. Both
  replicas hold the same single shard, so the 1.8x spread between them is read distribution.
  `api`'s busiest pod peaked at 0.268 of its 0.5-core limit (~54%) at `r500`'s worst moment; it was
  never stressed, which is *why* it barely scaled: `api-scaler`'s trigger
  (`sum(rate(cpu[2m]))/replicas` at `0.2`, confirmed live) works, and CPU demand didn't cross it
  until `r1000`
- **Relieved by** — no standing ceiling to relieve. The ramp saturation on `tei-embeddings`
  clears once KEDA finishes scaling out (`r500` clean at 13 replicas ~7 min in, `r1000` at 30
  replicas ~4 min in). Doubling per-pod CPU (commit `1ef1f0a`, 3/4→6/8 cores, applied before
  `r1000`) left this shape unchanged, because `tei-embeddings-scaler`'s target (1.5 cores/replica
  average) is far below both limits. The lever is scale-out speed: trigger threshold, poll
  interval, cooldown, pod-ready time

**Tier 2 — not attempted.** `M11`/`M12` (TEI-internal queue/duration, Qdrant search latency)
never landed. TEI's `/metrics` returns HTTP 200 with an empty body (`content-length: 0`, no
metrics flag in `text-embeddings-router --help`), which points at this image or version rather
than a missing scrape config; Qdrant's scrape job was added but never checked against real series
names. Declared, not measured, as in `report.md`'s Coverage.

No third tier is claimed. As in `01-ingestion` §3, the "component at its ceiling" template doesn't
fit a finding about convergence timing, which lives in the Matrix's `Converge` column and the
evidence bullet above.

### Guardrails

- **`tei-embeddings-scaler` `maxReplicaCount` = 30 (unchanged)** — not raised, although `r1000`
  ran right up against it: the real limit is the account's AWS Spot vCPU quota (256, checked live
  with `service-quotas`). At 6 cores requested per pod the quota alone caps headroom at ~35-40
  replicas whatever `maxReplicaCount` says, so raising it without a quota increase would trade a
  clean "ceiling hit" signal for pods stuck `Pending` · `tei-embeddings-scaler` → report §5
- **`tei-embeddings-scaler` trigger threshold** — not lowered, though Saturation argues for it.
  Lowering it (for example 1.5 → 1.0 cores/replica average) would make KEDA scale out ahead of a
  sudden step instead of during it, which targets the convergence lag directly. It is untested:
  there is no data on which threshold shortens convergence, only the diagnosis that threshold and
  speed are the lever
- **`api-scaler`: no change recommended.** Correctly configured and responding
  (`sum(rate(cpu[2m]))/replicas` against threshold `0.2`, scaled 2→3→6 as load rose); the open
  question from earlier in the campaign resolved to "working as intended"
- **Go API / TEI `limits.memory`** — not revised. Neither component showed memory pressure at
  any tested rate (not tracked in this Matrix, but no OOM or working-set warning surfaced in any
  point's Notes)
- **Query rate alert** — not set. `D15` is a lower bound (`≥1000`, untested above), so `D15 × 0.8`
  would alert on a number already known to be too low; better unset than built on an incomplete
  number
- **Latency alert** — not set: every p95 here is dominated by the fixed 2000ms mock delay, which
  real generation (Bedrock) won't reproduce, and a threshold tuned on mock data needs at least one
  real-Bedrock calibration point to transfer to production. This campaign never took one
- **Backfill `maxReplicaCount`** — not set. The contention pass never ran, so there is nothing to
  base it on

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — inverted, in a way `§1 Expected` didn't anticipate. TEI embedding as the
  ceiling was directionally right, but the plan framed it as a capacity ceiling to find at some
  rate. It is a convergence-speed cost: it appears at any rate above what the current replica
  count absorbs and resolves within minutes however high the rate goes. No rate in [50, 1000] was
  beyond the *system*; some it couldn't catch up with *fast enough* for a 10-minute window to look
  clean end to end
- **What should have been caught before the first run** — nothing in `§1 Validity` would have
  caught it. The Plan reads each point as one whole-window average and can't separate "still
  converging" from "steady state". `r500` and `r1000` both needed a manual time-series read after
  the fact; that read belongs in standard point analysis
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
- **Back into the kit** — two structural gaps. (1) The Saturation template's "component at its
  ceiling" framing has no slot for "the finding is in the Converge column", the same issue
  `01-ingestion` hit. (2) Window averages mislead when convergence is slow relative to the window.
  For a sudden large rate step, either extend the window well past expected convergence or have
  the runner report a separate converged-state statistic. Here the average had to be noticed as
  wrong and re-derived by hand, twice, just before the cluster went away. (3) The generator's own
  counters were never read. `dropped_iterations`, the VU pool's occupancy and k6's progress
  cadence each say when the generator stopped being the thing it claims to be, and all three were
  in the `.generator.log` files the whole time — the 2026-10-03 re-read found a 10.7<!--FD145-->%
  drop share at `r500`, 5.2<!--FD144-->% at `r1000` and a three-minute stall inside `r1000` that
  the Notes had written up as the system scaling in. A point's close should print them beside the
  Prometheus figures
