# simple-rag — Metric Inventory · report v1.0

Reference for `execution.md`. Four acquisition types:

**E**xported · **P**ulled · **C**alculated · **R**ecorded

E, P and C are recoverable after the fact. **R is not** — if it is not written down at the
time, the run is lost.

---

## E · Exported from Prometheus

One line per item in `scripts/queries.txt`. Confirm every name against the live endpoint
before writing the query — a wrong name returns NO DATA and is indistinguishable from a
missing scrape target.

### Cost inputs

- **E1** — SQS depth over time, both queues · `keda_scaler_metrics_value` · *scraped*
- **E2** — node count by instance type and capacity type ·
  `count by (label_node_kubernetes_io_instance_type, label_karpenter_sh_capacity_type) (kube_node_labels)` · *scraped*
- **E3** — node creation timestamps · `kube_node_created` · *scraped*
- **E4** — Karpenter nodeclaim lifecycle: launched, registered, terminated · **blocker**
- **E5** — Karpenter Spot interruption / disruption events · **blocker**
- **E16** — image pull duration · kubelet runtime operation duration, `pull_image` ·
  *confirm exposed*
- **E17** — egress bytes for the NAT per-GB line · Cilium eBPF metrics · *scraped*

### Constraint candidates

One line per component that could plausibly be the ceiling. An unlisted component cannot
be named as the constraint in §3.5.

- **E6** — worker CPU, chunker and indexer · cAdvisor container CPU rate · *scraped*
- **E7** — worker peak RSS, chunker and indexer · cAdvisor working set · *scraped*
- **E8** — TEI inference queue depth · `te_queue_size` · **blocker**
- **E9** — TEI inference duration · `te_request_inference_duration` · **blocker**
- **E10** — TEI effective batch size · `te_batch_next_size` · **blocker**
- **E11** — Qdrant write / upsert latency · confirm at `:6333/metrics` · **blocker**
- **E12** — Qdrant RSS · confirm at `:6333/metrics` · **blocker**
- **E13** — Qdrant `points_count` per collection · confirm at `:6333/metrics` · **blocker**

### Query path

- **E14** — Go API request latency histogram · confirm exposition in `apps/api` · **missing**
- **E15** — Go API error rate · same · **missing**

> **Why the blockers are hard blockers.** E1 tells you *that* throughput stopped growing;
> only E6–E13 tell you *what* stopped it. Without them §3.5 collapses to a single unproven
> guess, and Tier 2 — the reason for sweeping six points rather than four — cannot be
> claimed at all. Add via `ServiceMonitor` in each component's namespace with
> `labels.release` matching the Helm release, then verify `up{job="…"}`.

---

## P · Pulled from AWS

- **P1** — idle spend by `Component` tag, daily granularity, over the 24h E2 window ·
  Cost Explorer
- **P2** — S3 storage and Glacier IR charges · Cost Explorer
- **P3** — SQS request charges · Cost Explorer

> Most cost figures in this report are price-list arithmetic (R1), not billing exports.
> Only the idle window genuinely needs Cost Explorer — so tag activation blocks less than
> it appears to. Start the E2 window as soon as tags are live.

---

## C · Calculated — arithmetic, no run

Everything here carries ᴬ in the report.

- **C1** — docs/min per point = `R2.doc_count ÷ wall_time` · from R2, R3
- **C2** — throughput cross-check = derivative of E1
- **C3** — node-hours per point = E2 integrated over the run window · from E2, R3
- **C4** — `$/run` = `Σ (node_count × duration_hours × price_per_hour)`, spot and
  on-demand priced separately · from C3, R1
- **C5** — `$/1M docs` = `$/run ÷ docs_in_run × 1e6` · from C4, R2
- **C6** — warm-up share = `(provision + pull + init + consolidation tail) ÷ total
  node-hours` · from E3, E4, E16
- **C7** — marginal cost decomposition at the sweet spot · from C4, P2, P3, E17
- **C8** — effective `$/doc` across volumes = `(Block B floor + marginal × V) ÷ V` ·
  from P1, C7
- **C9** — Fargate equivalent = `vCPU-hours × price + GB-hours × price`, from measured pod
  requests × C3 · from C3, R1

> Run cost is computed, never read from a bill. AWS billing updates roughly daily and
> cannot see a twenty-minute run at all. Cost Explorer is used for the E2 window and
> nothing else.

---

## R · Recorded by hand — unrecoverable

### Before any run

**R1 · Price snapshot, dated.** Every instance type Karpenter may select, spot and
on-demand; `core-on-demand` and `database-on-demand` types; NAT hourly and per-GB; VPC
endpoints per AZ; EBS gp3; EKS control plane; S3 and Glacier IR; SQS; and Fargate
vCPU/GB rates for §4.4. Committed to `cost-model.xlsx`.

*Why nothing else produces it:* AWS prices change, and an undated price basis makes every
cost figure unverifiable. Run cost is computed from this rather than read from a bill.

**R2 · Fixture profile.** Exact document count, file count, pages median/p95/total,
characters, total bytes. From a one-off local PyMuPDF script, output committed to
`docs/report/data/corpus-profile.txt`.

*Why nothing else produces it:* the corpus can be overwritten and the profile cannot be
rebuilt from the report. The document count is the denominator of C1 and C5 — it is what
makes throughput computable from wall clock alone, with no per-worker instrumentation.

### During every run point

**R3 · Run log.** Point id, swept N, config commit, UTC start and end, anomaly count,
validity decision.

*Why nothing else produces it:* Prometheus does not know when a run began. A window
guessed a week later is a different run — and `export-metrics.py` takes `--start` and
`--end` as arguments.

**R4 · Saturation signal.** Which component was at its ceiling at this point, and the
metric it was read from. Candidates: chunker CPU (E6) · TEI queue depth (E8) · Qdrant
write latency (E11) · SQS not draining despite idle workers (E1).

*Why nothing else produces it:* no query returns "the chunker was the bottleneck". It is
a reading across E6–E13, and it is the entire raw material of the constraint ladder.

---

## Window boundaries

The most commonly mis-set values, and the usual reason a sweep gets thrown away.

- **Start** — the first `s3:ObjectCreated` event. The bulk upload script writes this
  timestamp; upload itself is outside the system under test.
- **End** — `apps-compute` NodePool at **zero nodes**, plus a 5-minute buffer.

The window does not close when the SQS queues drain. Nodes bill through `consolidateAfter`
and teardown, producing zero documents at full price — and that tail is precisely what
explains the unit-cost curve turning back up at high N (§3.4). Closing on "queue empty"
silently deletes the mechanism the report exists to demonstrate.

Extra points in an export are harmless. Missing ones require re-running the point at full
cost.
