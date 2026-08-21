# Execution · 02 · Inference · query path

| | |
| :--- | :--- |
| Produces | ⟨decided at Close⟩ · expected: the query-path section of report **v1.1**, or its own report |
| Preconditions | `00-baseline` §7.6 gate green · `01-ingestion` closed · Go API instrumented (E40–E49) · E20/E21/E30 landed |
| Data | `./data/` |
| Scripts | `./scripts/` |
| Status | **planned — Plan not frozen** |

> **This execution does not run in report v1.0.** It appears in the v1.0 coverage register
> as *Declared, not measured*, which is what lets that report ship at partial coverage
> instead of being split into two documents that each answer half a question.
>
> Nothing below is frozen. Freezing the Plan is the first act of running it.

---

# 1 · Plan  *(draft — freeze before the first point)*

### What this execution measures

What a query costs and what it costs to keep the query path responsive — latency
percentiles against arrival rate, the cost per thousand queries, and where the query path
and ingestion contend for the same Qdrant node.

### Why it is not part of v1.0

It has **its own frontier axis and its own denominator**. Ingestion is priced per document
at a concurrency N; queries are priced per query at an arrival rate R, against a different
replica count. Mixing the two produces a number that supports no decision. A single
fixed-replica latency measurement is a number without an axis — which is exactly what the
`p95 < 200 ms` line in `architecture.md` currently is, and it is labelled there as an
unverified design target rather than a result.

### Axis and points *(draft)*

| | |
| :--- | :--- |
| Varied | arrival rate R, at fixed API and TEI replicas — then replicas as a second pass |
| Values | ⟨coarse-to-fine, same rule as `01-ingestion`⟩ |
| Held constant | the collection produced by `01-ingestion` — restored from the `00-baseline` §8 snapshot, so the query path is measured against a known corpus |
| Unit of work | one query, counted when the response is written — **not** one document |

### Conditions *(draft)*

Baseline envelope applies in full. This execution adds a second denominator to the project,
which is acceptable only because it belongs to a different section — never to the same
table.

**Contention is the interesting condition.** Qdrant serves both paths from one node. A
query-load run against an idle ingestion path measures a system nobody runs. Decide before
freezing whether the axis includes concurrent ingestion, and say which claim each choice
supports.

### Instrumentation *(draft)*

Requires the range reserved in `00-baseline/metrics.md`:

| Ref | Metric | Status |
| :--- | :--- | :--- |
| E40– | Go API request rate, duration histogram, error rate | **not instrumented** — deliberately, until this run consumes them |
| E20, E21 | TEI queue depth and inference duration | pending ServiceMonitor |
| E30 | Qdrant read latency alongside write | pending ServiceMonitor |

Adding E40– is a prerequisite of this execution and is not done in v1.0: instrumentation
without a consumer generates work rather than evidence.

### Hypothesis

⟨Write it before the first point, dated. Not now — a hypothesis recorded a revision early
is a guess with a timestamp.⟩

---

# 2 · Journal

⟨Not started.⟩

---

# 3 · Close

⟨Not started.⟩

---

## Adjacent, and deliberately not this execution

**The retrieval-configuration study** — quantization variants, rescore and oversampling,
dense vs sparse vs hybrid, `hnsw_ef` sweep — is a **third execution**, not part of this one.
Its axis is retrieval configuration and its denominator is recall per query, not dollars per
query; folding it in here would put two axes in one execution and make neither attributable.

It also has a different shape: it runs **locally against the `00-baseline` §8 collection
snapshot, with no cluster**, which is the entire reason that snapshot is captured before
teardown. When it is scheduled, it becomes `executions/03-retrieval/` and INT8 scalar
quantization stops being a frozen given in `00-baseline` §2 and becomes that execution's
axis — returning to the baseline as a decided value in the following revision.

Until then, report v1.0 states quantization as a condition with no claim about its retrieval
cost, and carries the study in its out-of-scope table.
