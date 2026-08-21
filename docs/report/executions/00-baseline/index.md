# Execution · 00 · Baseline — simple-rag

| | |
| :--- | :--- |
| Produces | the givens every execution inherits, plus the idle floor (§5) |
| Preconditions | none — this is the first thing that happens |
| Data | `./data/` — constants, dated in the filename |
| Scripts | `./scripts/` — corpus profiler, one-off capture |
| Metrics | `./metrics.md` — the E register (extracted; §1 would otherwise be unreadable) |
| Status | ⟨planned · running · closed⟩ |
| Closed by | §7.6 gate green + §5 floor split |

> **Ownership rule — nothing in §1–§6 is the subject of a measurement.** Components,
> versions, models, frozen configuration, the corpus, the rate card: all givens.
> `01-ingestion` and `02-inference` cite these sections; they never restate them.
>
> If a value here becomes an axis, **it leaves this document** and becomes that execution's
> input. The winner returns here in the next revision.
>
> Worked example: `bge-small-en-v1.5` is the embedding model — a given, recorded in §1.6,
> not a finding. INT8 scalar quantization is a given, recorded in §2, chosen for memory
> footprint. The moment an execution named *"quantization variants"* exists, that parameter
> becomes its axis and is struck from here until it is decided again.
>
> The test is not "is it shared" but **"is it under test"**.

**One thing here is measured, and only one: §5, the floor.** It is measured with the system
deployed and idle, which is a state — not a run. That is why it lives in the baseline rather
than in an execution, and why it has no axis, no points and no unit cost.

---

# 1 · Components

One block per component. Configuration and exposed metrics live together, so adding a
component touches one place. Metric refs resolve in `./metrics.md`.

### 1.1 Platform · EKS + `core-on-demand`

| | |
| :--- | :--- |
| Version / identity | EKS ⟨version⟩ · addons ⟨⟩ |
| Placement | region ⟨⟩ · ⟨n⟩ AZ |
| Resources | `core-on-demand` NodePool — CoreDNS, ArgoCD, Cilium, Prometheus, Grafana, Loki |
| Elasticity | fixed — never reaches zero |

Refs: E2 (node inventory). This node group is the whole of Block A compute in §5.

⟨Note: the observability stack is not only the instrument. KEDA reads SQS depth through its
own scaler, and Prometheus is what every figure in this report is read from — an outage
during a run invalidates the point, not just the chart.⟩

### 1.2 Karpenter · NodePools

| | |
| :--- | :--- |
| Version / identity | chart ⟨⟩ |
| Placement | `core-on-demand` |
| Resources | four NodePools: `apps-compute` (Spot, ingestion) · `apps-serving` · `core-on-demand` · `database-on-demand` |
| Elasticity | `apps-compute` scales to zero · the other three do not |

Refs: E2, E3, E4 (node inventory and warm-up timestamps).

**`apps-compute` and `apps-serving` are pinned to a single instance type each for the whole
of `01-ingestion`** (§2). An unpinned pool lets Karpenter select a different type per point,
which makes points non-comparable and silently changes worker packing density — and packing
density is the mechanism report §3.4 exists to demonstrate.

`consolidateAfter` and the disruption policy are frozen in §2: they set the length of the
billed tail after the last document, which is half of the U-curve.

### 1.3 KEDA

| | |
| :--- | :--- |
| Version / identity | chart ⟨⟩ |
| Placement | `core-on-demand` |
| Resources | `ScaledJob` per stage · SQS queue-depth scaler · `pollingInterval` ⟨⟩ |
| Elasticity | floor 0 · ceiling `maxReplicaCount` — **this is the axis of `01-ingestion`** |

Refs: E1 (SQS depth as KEDA sees it).

> `maxReplicaCount` is recorded here as the knob that exists, not as a value. Its value is
> `01-ingestion`'s axis and does not belong to this document.

### 1.4 Stage 1 · chunker

| | |
| :--- | :--- |
| Version / identity | image digest ⟨sha256:…⟩ — frozen by `run-point.py --set-baseline` |
| Placement | `apps-compute`, Spot |
| Resources | requests ⟨cpu/mem⟩ · limits ⟨cpu/mem⟩ → ⟨n⟩ workers per node |
| Elasticity | KEDA `ScaledJob` on raw-document queue · floor 0 · ceiling N |

Refs: E10 (CPU), E11 (working set). PyMuPDF text extraction, single-threaded per document.

⟨Note: `MAX_ALLOWED_SIZE_BYTES` and chunks-per-SQS-message are frozen in §2 and become
guardrail rows in report §5 only if a measured number supports them.⟩

### 1.5 Stage 2 · indexer

| | |
| :--- | :--- |
| Version / identity | image digest ⟨sha256:…⟩ |
| Placement | `apps-compute`, Spot |
| Resources | requests ⟨cpu/mem⟩ · limits ⟨cpu/mem⟩ — currently `limits.memory: 2Gi` |
| Elasticity | KEDA `ScaledJob` on chunk queue · floor 0 · ceiling N |

Refs: E10, E11. Embeds via TEI, upserts to Qdrant with deterministic point IDs.

### 1.6 TEI · embedding service

| | |
| :--- | :--- |
| Version / identity | TEI ⟨version⟩ · `bge-small-en-v1.5` · 384 dim |
| Placement | `apps-serving` |
| Resources | replicas ⟨n⟩ · requests ⟨⟩ |
| Elasticity | ⟨fixed replicas · or scales to zero — **resolve in §7.5, it changes Block B**⟩ |

Refs: E20 (queue depth), E21 (inference duration) — both *pending* a ServiceMonitor.

### 1.7 Qdrant

| | |
| :--- | :--- |
| Version / identity | Qdrant ⟨version⟩ · collection ⟨name⟩ |
| Placement | `database-on-demand`, dedicated node, gp3 |
| Resources | instance type ⟨⟩ · EBS ⟨n⟩ Gi provisioned |
| Elasticity | fixed — cannot reach zero. Permanent Block B capacity |

Refs: E30 (write/upsert latency) — *pending*. `points_count` is deliberately not scraped;
see `./metrics.md`.

### 1.8 Object storage and queues · S3, SQS

| | |
| :--- | :--- |
| Version / identity | raw bucket ⟨⟩ · lifecycle → Glacier IR after 7 d · two SQS queues ⟨⟩ |
| Placement | regional services |
| Resources | — |
| Elasticity | storage variable with corpus size · request charges variable with traffic |

Refs: E1 (queue depth). S3 `ObjectCreated` is the run-window opening signal for
`01-ingestion`.

### 1.9 Network egress · NAT Gateway, VPC endpoints

| | |
| :--- | :--- |
| Version / identity | one NAT ⟨per AZ / single⟩ · Interface Endpoints: Bedrock, SQS, S3 |
| Placement | VPC |
| Resources | — |
| Elasticity | NAT hourly charge is fixed · per-GB is variable · endpoints billed per AZ per hour |

Refs: E5 (egress bytes).

> **The hidden line of this architecture class.** The NAT bills hourly regardless of
> traffic, and again per gigabyte — including container image pulls and the indexer's model
> weight downloads. It is omitted from almost every published version of this design.

### 1.10 Go API · query path

| | |
| :--- | :--- |
| Version / identity | image digest ⟨⟩ |
| Placement | `apps-serving` |
| Resources | replicas ⟨n⟩ |
| Elasticity | fixed |

**Present in the system, not under test in report v1.0, and deliberately not instrumented.**
Request metrics have no consumer until `02-inference` exists — instrumentation without a
consumer generates work rather than evidence. Range E40–E49 is reserved for it.

### 1.11 Elasticity summary

Decides whether any claim about elastic cost survives contact with a bill.

| Component | Scales on | Floor | Ceiling |
| :--- | :--- | :--- | :--- |
| chunker / indexer | SQS depth (KEDA) | **0** | N |
| `apps-compute` nodes | pod pressure (Karpenter) | **0** | ⟨⟩ |
| TEI | ⟨resolve §7.5⟩ | ⟨⟩ | ⟨⟩ |
| Qdrant | — | 1 node, always on | 1 |
| `core-on-demand` | — | always on | — |
| NAT, VPC endpoints, EKS control plane | — | always on | — |

**Consequences.** Exactly one path in this system reaches zero: ingestion compute. Every
other line is permanent and belongs to the floor. The observability stack is shared with
other workloads and is therefore Block A, not Block B — but it is also part of the system
under test, because KEDA scales on a metric it serves.

---

# 2 · Configuration freeze

Decided once, before the first point of `01-ingestion`. Changing any of these invalidates
comparability across points; changing them between executions means a new revision of this
document.

| Parameter | Value | Why it must be frozen |
| :--- | :--- | :--- |
| `apps-compute` instance type | ⟨type⟩ | Unpinned, Karpenter picks a different type per point: points become non-comparable and packing density moves silently |
| Workers per node (resulting) | ⟨~n⟩ | Dense packing amortises warm-up and shifts the sweet spot right. A condition of the result, not a detail |
| `apps-serving` instance type | ⟨type⟩ | Same, for TEI |
| `database-on-demand` instance type | ⟨type⟩ | Sets the Block B headline line |
| Karpenter `consolidateAfter` | ⟨value⟩ | Sets the length of the billed tail after the last document — half the mechanism of the U-curve (report §3.4) |
| Karpenter disruption policy / budgets | ⟨value⟩ | Node churn mid-run adds warm-up that belongs to no concurrency level |
| Which `ScaledJob` N applies to | ⟨indexer only / both stages⟩ | Follows from the Tier 1 hypothesis; a knob on a non-constraint produces a flat curve |
| KEDA `pollingInterval` | ⟨s⟩ | Sets scale-up latency, which lands inside the measured window |
| chunker / indexer requests + limits | ⟨⟩ | Determines packing density; changing it changes node-hours at constant N |
| Qdrant `optimizers_config.indexing_threshold` | ⟨value⟩ | HNSW rebuilt during bulk ingest inflates E30 for a reason unrelated to saturation, misattributing Tier 2 |
| Scalar Quantization | **on** (INT8) | Fixed parameter, chosen for memory footprint. Retrieval cost not measured in v1.0 — stated as a condition, never as a finding |
| Qdrant state between points | **wiped** (`--wipe-mode recreate`) | A growing collection raises write latency, which is exactly the E30 signal Tier 2 may rest on |
| TEI replicas | ⟨n⟩ | If it moved with N, the ladder would have two axes and no tier would be attributable |
| `MAX_ALLOWED_SIZE_BYTES` | ⟨confirm 100 MB⟩ | Changes which corpus tail is processed at all — silently changes the denominator |
| Chunks per SQS message | ⟨confirm 30⟩ | Sets SQS request count per document, a line in report §4.2 |
| SQS visibility timeout | ⟨s⟩ | Too low, documents are processed twice and the denominator lies |
| S3 lifecycle → Glacier IR | 7 d | A storage-class line in §5 |
| Region · AZ count | ⟨⟩ · ⟨n⟩ | Prices and per-AZ endpoint charges |

Frozen by ⟨⟩ · Date ⟨⟩ · Commit ⟨⟩

---

# 3 · Input fixture

> **Yields:** the denominator of every unit-cost figure in the report.
> **From:** `./scripts/profile-corpus.py` (PyMuPDF, local, no cluster) →
> `./data/corpus-profile.txt`.
> **Before any run:** profile first, then freeze. A corpus that changes between points makes
> the run matrix meaningless — and the profile cannot be rebuilt once the corpus is
> overwritten.

| | |
| :--- | :--- |
| Source | `zabiullah/pdf-books-collection` (HuggingFace) |
| Snapshot location | ⟨S3 prefix⟩ |
| File count | ⟨⟩ |
| **Exact document count** | ⟨⟩ ← the denominator |
| Pages — median · p95 · total | ⟨⟩ |
| Extracted characters — total · median per file | ⟨⟩ |
| Total bytes | ⟨⟩ |
| Freeze date · commit | ⟨⟩ |

**Unit of work:** ⟨one sentence — e.g. one PDF ingested end to end, counted when its final
chunk batch is acknowledged by Qdrant⟩. Everything downstream is priced per this unit.

*How to read the distribution: the median is the typical file — half the corpus is shorter.
The p95 is the tail, and the tail drives worst-case memory (E11) and parse time.*

**One denominator, not two.** A per-page figure transfers better to another corpus but
doubles every table in report §3 and §4 for a conversion the reader can perform from the
distribution above.

**Why the exact count matters beyond description:** because the corpus is frozen, throughput
is computable from wall clock alone (C1), with no per-worker instrumentation.

---

# 4 · Price basis

> **Before any run:** unrecoverable afterwards. Rates change, and an undated basis makes
> every derived figure unverifiable.

Short list, because the NodePools are pinned (§2) — roughly three instance rows rather than
forty.

- [ ] Pinned `apps-compute` instance type — **Spot and On-Demand**, $/hour
- [ ] Pinned `apps-serving` instance type — Spot and On-Demand, $/hour
- [ ] `core-on-demand` instance type — $/hour
- [ ] `database-on-demand` instance type — $/hour
- [ ] NAT Gateway — $/hour **and** $/GB processed
- [ ] VPC Interface Endpoints — $/hour per endpoint per AZ (Bedrock, SQS, S3)
- [ ] EBS gp3 — $/GB-month (+ provisioned IOPS/throughput if above baseline)
- [ ] EKS control plane — $/hour
- [ ] S3 Standard + Glacier Instant Retrieval — $/GB-month, request classes
- [ ] SQS — $/1M requests
- [ ] **Fargate — $/vCPU-hour and $/GB-hour** (report §4.4 break-even)

Date captured: ⟨⟩ → `./data/price-⟨YYYY-MM-DD⟩.csv` · committed to `cost-model.xlsx`

**Run cost is computed from this, never read from a bill.** AWS billing aggregates roughly
daily and cannot see a twenty-minute run at all. Billing exports are used for §5 and nothing
else.

*Dating two partial snapshots costs more than taking one complete one — including the rates
only `02-inference` will need.*

---

# 5 · Floor — cost at zero load

> **From:** the idle window in §7.4, pulled by tag from Cost Explorer.
> **Before the window:** attribution live and **activated** (§7.1); corpus already in S3;
> zero activity for the full window.
> Lines Cost Explorer cannot resolve are computed from §4 and marked ᴬ.

Split rather than totalled: for anything claiming elastic economics the floor is the entire
argument, and it is where published architectures are least honest.

| Block | What it is | $/month |
| :--- | :--- | :--- |
| A | shared platform — exists without this feature | |
| **B** | **feature-dedicated — disappears with it. The BLUF number** | |
| C | standalone greenfield — A + B | |

**Not divided by an assumed number of tenant features.** That divisor would be arbitrary,
and Blocks B and C already answer both questions a reader can ask.

### Block A — shared platform

| Line | Fixed / Variable | $/month | Note |
| :--- | :--- | :--- | :--- |
| EKS control plane | Fixed | | plan assumes ~$73 — verify |
| `core-on-demand` node group | Fixed | | CoreDNS, ArgoCD, Cilium, Prometheus, Grafana, Loki |
| NAT Gateway — hourly | Fixed | | |
| NAT Gateway — per-GB processed | Variable | | cross-check against E5 |
| EBS gp3 — Prometheus 10 Gi + Loki 10 Gi | Fixed | | |
| **Block A total** | | | |

### Block B — feature-dedicated · the headline

| Line | Fixed / Variable | $/month | Note |
| :--- | :--- | :--- | :--- |
| `database-on-demand` node group — Qdrant | Fixed | | instance class explained below |
| EBS gp3 — Qdrant volume | Fixed | | billed on provisioned size, not usage |
| TEI serving capacity at idle | ⟨fixed / scale-to-zero — §7.5⟩ | | |
| VPC Interface Endpoints — Bedrock, SQS, S3 × AZ | Fixed | | |
| S3 storage — raw + Glacier IR after 7 d | Variable with corpus size | ᴬ | from §3 bytes × §4 rate |
| SQS requests | Variable | | ≈ 0 at idle |
| KEDA `ScaledJob` ingestion compute | Variable, floor 0 | **0.00** | the one genuinely zero row |
| **Block B total** | | | |

### Three notes this table exists for

*Lines billed regardless of traffic.* EKS control plane, NAT hourly, VPC endpoints per AZ,
both permanent node groups, every provisioned EBS volume. None of them care whether a
document was ever ingested.

*Lines billed per unit of data moved.* NAT per-GB, including image pulls and HuggingFace
weight downloads; S3 and SQS request classes.

*Quantization sets the database instance class.* At 1M points × 384 dim, float32 vectors
need 1.536 GB and INT8 needs 0.384 GB ᴬ — which is why the `database-on-demand` line is as
small as it is. Measured Qdrant RSS at teardown: ⟨§8⟩. The retrieval cost of this
compression is **not measured in v1.0** and is not claimed either way.

*The prior public claim.* Article 1 advertised "$0.00 on idle". This table states for
exactly how many rows that is true — a deepening of the claim with data in hand, not a
retraction. Report §4.1 carries this sentence to the reader.

---

# 6 · Envelope

Conditions under which every figure downstream holds. Each execution adds its own on top.

> These figures hold for ⟨corpus shape from §3 — text-layer PDFs, median ⟨n⟩ pages⟩ on
> **EKS in ⟨region⟩**, with a Karpenter Spot NodePool pinned to `⟨instance type⟩` for
> ingestion (≈ ⟨n⟩ workers per node), Qdrant self-hosted on a dedicated On-Demand gp3 node
> with INT8 scalar quantization and `indexing_threshold = ⟨value⟩`, and `bge-small-en-v1.5`
> at 384 dimensions served by TEI on `apps-serving`. Outside these conditions, re-measure.

Deliberately outside it: scanned PDFs requiring OCR · GPU-backed embedding · corpora above
⟨n⟩ GB · multi-region · any managed vector database.

---

# 7 · How this was established

The working record. Nothing below is cited by other executions.

**Ordering constraint that decides the whole schedule:** §7.1 is forward-only and takes up
to 24 h to appear in Cost Explorer; §7.4 needs a full clean day *after* that; and no point
of `01-ingestion` may fall inside the §7.4 window. Everything else can run in parallel.

## 7.1 Cost attribution

Not retroactive. Longest lead time of anything here — do it first.

- [ ] `default_tags` in `terraform/envs/prod/providers.tf`: `Project = simple-rag`,
  `Component` (`platform` / `database` / `ingest`), `CostGroup = benchmark`
- [ ] Karpenter-created nodes and volumes carry the tags — set in the `EC2NodeClass`, not
  only in `default_tags`; provider tags do not reach resources Karpenter creates
- [ ] Rolled out — every module overrides `Component` correctly
- [ ] **Activated** in Billing → Cost Allocation Tags. A separate step from tagging,
  forward-only, up to 24 h before data appears
- [ ] Verified on a live resource in the console, not in plan output

Date attribution went live: ⟨⟩

> Without this, Cost Explorer returns one undifferentiated number and §5 cannot be split.
> It is the most common reason a cost report is impossible rather than merely late.

## 7.2 Observability verification

Verified by query, not by reading config.

**Required before any execution:**

- [ ] `up == 0` returns empty
- [ ] E1 · E2 · E3 · E4 · E5 · E10 · E11 return data, with the filters the executions will
  actually use (`./metrics.md` → Mandatory filtering)
- [ ] E4 pod-side name confirmed against the installed kube-state-metrics version
  (`kube_pod_start_time` or the ready-time variant)
- [ ] Prometheus retention noted: ⟨3 d⟩ → export after **every** point, no exceptions
- [ ] KEDA's own scaler metric is served by the same Prometheus the runs are read from — an
  outage during a point invalidates the point, not only the chart

**Optional — gates report §3.5 Tier 2 only. Not a gate for the runs:**

- [ ] E20, E21 — TEI ServiceMonitor
- [ ] E30 — Qdrant ServiceMonitor on `:6333/metrics`
- [ ] Karpenter ServiceMonitor — **15-minute timebox.** Take it if
  `serviceMonitor.enabled` works first try; otherwise abandon. `run-point.py` detects node
  loss as a change in the node set while the queue is non-empty

> A component that is not observed cannot be named as a constraint, because an absent series
> looks exactly like an idle one. But an optional metric blocks one claim, not the report:
> Tier 1 reads from E10, which is scraped today. If TEI and Qdrant land before the
> refinement points, Tier 2 is claimable from the points that have them. If they never land,
> one tier is reported and the second goes to report "Out of scope" — which is what the
> report's own rule already requires of an unproven tier.
>
> Add via `ServiceMonitor` in each component's namespace with `labels.release` matching the
> Helm release, then verify `up{job="…"}`.

**Confirmed names.** Read each off the live endpoint, then write it into `./metrics.md`.

| Ref | Component | Name as exposed | Copied to metrics.md |
| :--- | :--- | :--- | :--- |
| E4 | kube-state-metrics | | |
| E20 | TEI | | |
| E21 | TEI | | |
| E30 | Qdrant | | |

## 7.3 Constants captured → `./data/`

Dated in the filename. Re-capturing later means a new file, never an overwrite.

- [ ] **Prices** → `./data/price-⟨date⟩.csv` — §4, complete in one pass
- [ ] **Corpus profile** → `./data/corpus-profile.txt` — §3
- [ ] **Configuration snapshot** → `./data/cluster-config-⟨date⟩.json` — §2 values as
  actually applied, not as written in Git
- [ ] **Artifact identity** → `./data/image-digests-⟨date⟩.json` — chunker and indexer,
  from `run-point.py --set-baseline`

## 7.4 Idle window → §5

- [ ] Corpus **already uploaded** to S3 before the window opens — otherwise the storage line
  of Block B is measured as zero and the floor is understated
- [ ] Ingestion triggering disabled for the duration (`ScaledJob` paused, or S3
  notifications suspended) — decided and applied **before** the window, never inside it
- [ ] Scheduled so that **no `01-ingestion` point falls inside it.** One point inside
  destroys the window and costs a full day
- [ ] **Aligned to UTC midnight → midnight.** Cost Explorer's daily granularity otherwise
  mixes the setup day into the idle day, and the split is unrecoverable. If hourly
  granularity is enabled instead, record that it was
- [ ] Zero workload and zero human activity: no deploys, no config changes, no manual
  commands. ArgoCD reconciliation stays on — it is part of the floor
- [ ] Window spans a full daily cycle: backups, rotations, scheduled jobs
- [ ] **Proof of idleness exported**, not asserted: E1 flat at zero and E2 constant across
  the window → `./data/idle-window-proof.json`. An idle window with no evidence of idleness
  is one unverifiable number

Window UTC: start ⟨⟩ → end ⟨⟩ · Cost Explorer data available from ⟨+24 h⟩

**Pull:** spend by tag, daily granularity, grouped by `Component`.

| `Component` tag | $/day | → Block |
| :--- | :--- | :--- |
| `platform` | | A |
| `database` | | B |
| `ingest` | | B |
| untagged / shared | | ⟨resolve before writing §5⟩ |

Untagged spend resolved? ⟨⟩ — an unresolved untagged line means the A/B split is an
estimate, and every row derived from it must be marked ᴱ.

## 7.5 Open verification

Facts that must be confirmed rather than assumed, because a wrong assumption fails silently
rather than loudly.

| Item | What it invalidates if wrong | Resolved |
| :--- | :--- | :--- |
| Does TEI actually scale to zero at idle? | The Block B headline, and the BLUF idle row | |
| Do Karpenter-created nodes and EBS volumes carry the cost tags? | The entire A/B split — ingestion nodes would land in "untagged" | |
| Does `keda_scaler_metrics_value` carry a label distinguishing the two queues? | E1, and the drain-rate cross-check C2 | |
| Pod-side warm-up metric name in the installed kube-state-metrics | E4 → C6 → report §3.4, the mechanism of the U-curve | |
| Does the Cilium egress series separate NAT-bound traffic from cluster-internal? | E5 and the NAT per-GB line | |
| Number of VPC Interface Endpoints × AZ actually deployed | A fixed Block B line, commonly undercounted | |
| Is `points_count` reachable over REST from where `run-point.py` runs? | Per-point completeness check in `01-ingestion` | |

## 7.6 Gate

- [ ] §7.1 green — attribution live, date recorded
- [ ] §7.2 required rows green
- [ ] §2 frozen, by name and date
- [ ] §7.3 constants captured and dated
- [ ] §7.4 window closed and §5 split into A / B / C
- [ ] §7.5 resolved, or the affected figure marked ᴱ
- [ ] `run-point.py` dry-run clean

Date: ⟨⟩ · Optional items still open, and which claim each puts at risk: ⟨⟩

> **`01-ingestion` may start before the §5 numbers exist.** The gate rows that block it are
> §2, §7.2-required and §7.3. Cost Explorer data for §7.4 arrives a day late and blocks only
> report §4.1 and §4.3. Waiting for a bill to start a sweep costs a day and buys nothing.

---

# 8 · Teardown artifacts

Captured after the **final** execution of this revision, before anything is destroyed.
Fifteen minutes, and it is what makes the retrieval-configuration study possible later
without a cluster.

```bash
curl -X POST "http://localhost:6333/collections/${COLL}/snapshots"
curl -o corpus-v1.snapshot \
  "http://localhost:6333/collections/${COLL}/snapshots/${SNAPSHOT_NAME}"
aws s3 cp corpus-v1.snapshot s3://<bucket>/fixtures/qdrant/corpus-v1.snapshot
```

- [ ] Snapshot uploaded → `s3://<bucket>/fixtures/qdrant/corpus-v1.snapshot` ·
  checksum ⟨⟩
- [ ] `MANIFEST.md` alongside it: Qdrant version, embedding model and dimension, chunker
  image digest, `GET /collections/<name>` output, `corpus-profile.txt`
- [ ] One `kubectl top pod` reading of the Qdrant pod → the "smallest viable instance class"
  line in §5 Block B: ⟨⟩
- [ ] `./data/` committed and pushed

*Why nothing else produces it:* re-parsing and re-embedding a book-length PDF corpus costs
hours of CPU and cannot be reconstructed from the report. This snapshot is the input
artifact of the retrieval-configuration study declared out of scope in report v1.0 — and the
reason that study can run locally, at any later date, without a cluster.
