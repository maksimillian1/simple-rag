# simple-rag — Metric Inventory · report v1.0

Reference for `execution.md`. Four acquisition types:

**E**xported · **P**ulled · **C**alculated · **R**ecorded

E, P and C are recoverable after the fact. **R is not** — if it is not written down at the
time, the run is lost.

> **Naming.** Runs are named, metrics are numbered. Two runs: `sweep` (ingestion
> concurrency) and `idle` (24h floor window). Point ids are `sweep-n04`, `sweep-n12`, …
> This avoids the collision where a single id meant both a run and a metric.

---

## E · Exported from Prometheus

Nine series. One line per item in `scripts/queries.txt`. Confirm every name against the
live endpoint before writing the query — a wrong name returns NO DATA and is
indistinguishable from a missing scrape target.

### Cost inputs · E1–E4 — required before the first point

- **E1** — SQS depth over time, both queues · `keda_scaler_metrics_value` · *scraped*
- **E2** — node count by instance type and capacity type ·
  `count by (label_node_kubernetes_io_instance_type, label_karpenter_sh_capacity_type) (kube_node_labels)` · *scraped*
- **E3** — warm-up window: node creation and first-pod-ready timestamps ·
  `kube_node_created` and `kube_pod_start_time` · *scraped* · confirm the pod-side name
  against kube-state-metrics before writing the query
- **E4** — egress bytes for the NAT per-GB line · Cilium eBPF metrics · *scraped*

### Constraint candidates · E5–E9

One line per component that could plausibly be the ceiling. An unlisted component cannot
be named as the constraint in §3.5.

- **E5** — worker CPU, chunker and indexer · cAdvisor container CPU rate · *scraped* ·
  **this is the Tier 1 proof**, and it is available today
- **E6** — worker peak RSS, chunker and indexer · cAdvisor working set · *scraped* ·
  source of two guardrails
- **E7** — TEI inference queue depth · `te_queue_size` · *ServiceMonitor pending*
- **E8** — TEI inference duration · `te_request_inference_duration` · *ServiceMonitor pending*
- **E9** — Qdrant write / upsert latency · confirm at `:6333/metrics` ·
  *ServiceMonitor pending*

> **E7, E8 and E9 are not blockers.** They are required for **§3.5 Tier 2 only**.
> Tier 1 reads from E5, which is scraped today. The sweep starts without them; if the
> ServiceMonitors land before the refinement points, Tier 2 is claimable from the points
> that have them. If they do not land, one tier is reported and the second goes into
> "Not covered" — which is what the report's own rule already requires of an unproven
> tier.
>
> Add via `ServiceMonitor` in each component's namespace with `labels.release` matching
> the Helm release, then verify `up{job="…"}`.

**Two ServiceMonitors, both optional.** Go API metrics are not instrumented — no
query-path run exists to consume them. Karpenter's own ServiceMonitor is worth a
15-minute attempt if the Helm chart exposes `serviceMonitor.enabled` — free insurance on
interruption events — and is abandoned at 15 minutes, because `run-point.py` detects node
loss as a change in the node set while the queue is non-empty.

**Not a Prometheus series, by choice.** Qdrant `points_count` is one value at the end of a
run, read over REST by `run-point.py`. Qdrant RSS is one reading at teardown (R5). Node
warm-up sub-phases — provisioning, image pull, runtime init — are not separated: §3.4
needs the overhead *share*, not its attribution.

---

## P · Pulled from AWS

- **P1** — idle spend by `Component` tag, daily granularity, over the 24h `idle` window ·
  Cost Explorer
- **P2** — S3 storage and Glacier IR charges · Cost Explorer
- **P3** — SQS request charges · Cost Explorer

> Most cost figures in this report are price-list arithmetic (R1), not billing exports.
> Only the idle window genuinely needs Cost Explorer — so tag activation blocks less than
> it appears to. Start the `idle` window as soon as tags are live.

---

## C · Calculated — arithmetic, no run

Everything here carries ᴬ in the report.

- **C1** — docs/min per point = `R2.doc_count ÷ wall_time` · from R2, R3
- **C2** — throughput cross-check = derivative of E1
- **C3** — node-hours per point = E2 integrated over the run window · from E2, R3
- **C4** — `$/run` = `node_hours × price_per_hour`, spot and on-demand priced
  separately · from C3, R1 · **single instance type per pool** (see R1), so this is a
  product, not a sum over types
- **C5** — `$/1M docs` = `$/run ÷ docs_in_run × 1e6` · from C4, R2
- **C6** — warm-up share = `((node_created → first_pod_ready) + consolidation tail) ÷
  total node-hours` · from E3, E2
- **C7** — marginal cost decomposition at the sweet spot · from C4, P2, P3, E4
- **C8** — effective `$/doc` across volumes = `(Block B floor + marginal × V) ÷ V` ·
  from P1, C7
- **C9** — Fargate equivalent = `vCPU-hours × price + GB-hours × price`, from measured pod
  requests × C3 · from C3, R1
- **C10** — vector memory arithmetic, float32 vs INT8 SQ, at 1M points × 384 dim ·
  from R1 · explains the `database-on-demand` instance class, does not measure it

> Run cost is computed, never read from a bill. AWS billing updates roughly daily and
> cannot see a twenty-minute run at all. Cost Explorer is used for the `idle` window and
> nothing else.

---

## R · Recorded by hand — unrecoverable

### Before any run

**R1 · Price snapshot, dated.** Committed to `cost-model.xlsx`.

`apps-compute` and `apps-serving` are **pinned to a single instance type each for the
duration of the sweep**, so this is roughly three rows rather than forty: the pinned
ingestion type (spot and on-demand), `core-on-demand`, `database-on-demand`. Plus NAT
hourly and per-GB; VPC endpoints per AZ; EBS gp3; EKS control plane; S3 and Glacier IR;
SQS; and Fargate vCPU/GB rates for §4.4.

*Why nothing else produces it:* AWS prices change, and an undated price basis makes every
cost figure unverifiable. Run cost is computed from this rather than read from a bill.

*Why pinning matters beyond convenience:* an unpinned NodePool lets Karpenter select a
different type per point, which makes points non-comparable and silently changes worker
packing density — and packing density is the mechanism §3.4 exists to demonstrate.

**R2 · Fixture profile.** Exact document count, file count, pages median/p95/total,
characters, total bytes. From a one-off local PyMuPDF script, output committed to
`docs/report/data/corpus-profile.txt`.

*Why nothing else produces it:* the corpus can be overwritten and the profile cannot be
rebuilt from the report. The document count is the denominator of C1 and C5 — it is what
makes throughput computable from wall clock alone, with no per-worker instrumentation.

### During every run point

**R3 · Run log.** Point id, swept N, config commit, UTC start and end, anomaly count,
validity decision.

*Emitted by `run-point.py`* — the script writes the whole block to
`docs/report/data/<point>.point.md`. Recorded here because Prometheus does not know when
a run began, and a window guessed a week later is a different run.

**R4 · Saturation signal.** Which component was at its ceiling at this point, and the
metric it was read from. Candidates: chunker CPU (E5) · TEI queue depth (E7) · Qdrant
write latency (E9) · SQS not draining despite idle workers (E1).

*Why nothing else produces it:* no query returns "the chunker was the bottleneck". It is
a reading across E5–E9, and it is the entire raw material of the constraint ladder.
**This is the only field of the point block the script cannot fill.** Read it in Grafana
immediately after the point, while the window is fresh.

### At teardown — once

**R5 · Teardown artifacts.** Captured after the final sweep point, before the cluster is
destroyed.

- Qdrant collection snapshot → `s3://<bucket>/fixtures/qdrant/corpus-v1.snapshot`,
  with checksum
- Alongside it: Qdrant version, embedding model and dimension, chunker image digest,
  `GET /collections/<name>` output, `corpus-profile.txt`
- One `kubectl top pod` reading of the Qdrant pod, for the "smallest viable instance
  class" line in §4.1 Block B

*Why nothing else produces it:* re-parsing and re-embedding a book-length PDF corpus costs
hours of CPU and cannot be reconstructed from the report. The snapshot is the input
artifact of the retrieval-configuration study declared in "Not covered", and it is the
reason that study can be run locally at any later date without a cluster.

---

## Window boundaries

The most commonly mis-set values, and the usual reason a sweep gets thrown away.
Enforced by `run-point.py`; stated here because the script encodes this rule and nothing
else explains it.

- **Start** — the first `s3:ObjectCreated` event. The bulk upload script writes this
  timestamp to a marker file consumed by `--start-marker`; upload itself is outside the
  system under test.
- **End** — `apps-compute` NodePool at **zero nodes**, plus a 5-minute buffer.

The window does not close when the SQS queues drain. Nodes bill through `consolidateAfter`
and teardown, producing zero documents at full price — and that tail is precisely what
explains the unit-cost curve turning back up at high N (§3.4). Closing on "queue empty"
silently deletes the mechanism the report exists to demonstrate.

