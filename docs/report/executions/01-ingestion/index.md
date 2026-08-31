# 01 · Ingestion concurrency

- **Why this execution exists** — how throughput and unit cost respond to ingestion concurrency on a Spot pool that scales to zero: how do we configure it?
- **Produces** — the efficiency frontier, the constraint ladder, and the marginal cost per document that report §4 cannot compute itself
- **Expected** — recorded ⟨date⟩, before the first run. Tier 1 is the Stage-1 chunker, not TEI. PyMuPDF extraction is single-threaded CPU work and may dominate embedding time by an order of magnitude, while the original design assumed inference would saturate first. Corollary: the unit-cost minimum sits below the throughput knee, driven by warm-up share rather than by any component ceiling
- **Status** — ⟨planned · running · closed · abandoned⟩
- **Plan frozen** — ⟨date⟩ · commit `⟨sha⟩`
- **Givens** — `00-baseline` §2, cited from there

---

## 1 · Plan

### Axis

- **Varied parameter** — KEDA `maxReplicaCount` (N), one value on both ScaledJobs, in `deploy/k8s/apps/⟨…⟩/scaledjob.yaml`. Fixing one stage while sweeping the other makes the fixed stage the ceiling by construction, and the hypothesis names a stage. The split between them comes from M6 → K7
- **Candidate grid** — N ∈ {4, 8, 12, 16, 20, 24}
- **Sweep order** — coarse to fine: {4, 12, 24}, then two refinement points placed by the shape those three produce (`methodology.md` §7). Five points total
- **Held constant** — image digests, corpus (`zabiullah/pdf-books-collection`, 1,041 PDFs, 14.52 GB — provisioned via `../../scripts/download-pdf-books-dataset.py` + `upload-dir-to-s3.py`), Qdrant collection config, instance types, the TEI trigger, and every row of `00-baseline` §2 Configuration freeze. The config commit moves between points: the swept value lives in Git
- **Not held constant, and measured instead** — TEI replicas. The indexer drives the same autoscaler the query path drives, so TEI scales during a run and its cost above the two-replica floor belongs to this execution → K5
- **Reset between points** — both queues at zero, `apps-compute` at zero nodes, TEI back at 2 replicas, collection recreated
- **Conditions carried to report §2** — bulk-drop arrival, worker packing density of ≈ ⟨n⟩ per node → K2, and the TEI trigger frozen in `00-baseline` §2

### Window

- **Opens** — first `s3:ObjectCreated`, from the marker the upload script writes · recorded by `run-ingestion-point.py --start-marker`. Upload is outside the system under test
- **Closes** — `apps-compute` at zero nodes **and** TEI back at 2 replicas, plus ⟨5⟩ min. Not at queue drain → K1
- **Spacing** — one point per clock hour → K6
- **Excluded from the window** — query load. TEI is shared, and its scale-out would be priced in two executions at once → K5

### Metrics

The register is in `./metrics.md`. PromQL for M1–M9 is in `./data/series.txt` and `./data/guards.txt`, confirmed names only, dry run clean ⟨date⟩.

### Validity

| Condition | Action | Ref |
| :--- | :--- | :--- |
| image digests, corpus or `00-baseline` §2 differ from the other points | exclude | |
| reset did not run — collection not recreated, or TEI above 2 at open | exclude | K5 |
| the window shares an hourly CUR bucket with another point | exclude | K6 |
| M1 does not fall steadily | not trusted — the wall time behind D22 describes a stall | |
| M5 disagrees with N | file the point under M5, both numbers in the matrix | K7 |
| a node was lost during the window | re-run, or mark ᴱ and drop it from the curve fit | K1 |
| R21 differs from the frozen corpus count | re-run — the denominator lies | |
| split cost allocation returns no rows for the point's pods | keep the cost row, drop the M12 decomposition | K5 |
| M8 non-zero | the cost row stands; the memory guardrail it fed is void | K3 |

Averaging an excluded point back in silently is not a third option.

---

## 2 · Journal

One invocation per point. The runner does preflight, window timing, interruption detection, the
R21 read, Prometheus export, and the TEI and Qdrant reset. It does not read cost. Exit codes and
what to do with each are in `run-ingestion-point.py --help`.

```bash
../../scripts/run-ingestion-point.py --run ingestion-n04 --n 4
```

The cost pass runs once for the whole campaign, at least 48 h after the last point, over the
windows recorded in R19 → K6:

```bash
../../scripts/aws-cur-report-export.py --data s3://⟨bucket⟩/⟨prefix⟩ \
                            --start ⟨window start⟩ --hours 1 \
                            --tag feature=⟨value⟩ --split --format csv
```

One invocation per point window. The serving pool idle rate from `00-baseline` §2 is subtracted
before the figures land in `./data/frontier.csv`.

### Run ledger

| # | Point | Window UTC | Commit | Outcome | Signal | Exported | Cost read |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | ingestion-n04 | ⟨HH:MM → HH:MM⟩ ᴿ | `⟨sha⟩` | ⟨ok · aborted, ⟨reason⟩ · invalid, ⟨reason⟩⟩ | ⟨component at its ceiling · headroom⟩ ᴿ | ⟨✓ · —⟩ | ⟨✓ · —⟩ |
| 02 | ingestion-n12 | | | | | | |
| 03 | ingestion-n24 | | | | | | |
| 04 | ingestion-n⟨⟩ | | | | | | |
| 05 | ingestion-n⟨⟩ | | | | | | |

`Exported` is filled when the run ends. `Cost read` is filled by the cost pass, days later, and
a blank there after the pass ran is a lost cost row rather than a lost point.

### Notes

**Corpus provisioning** — 1,041 PDFs (14.52 GB) uploaded to the raw-docs bucket in 387 s
(37.6 MB/s) via `download-pdf-books-dataset.py` + `upload-dir-to-s3.py` (16 workers, 16 MB
multipart threshold). Throughput matched the operator's home uplink, not S3 or the
scripts' concurrency — the HF download side independently ran at a comparable ~34 MB/s. Not
a system-under-test figure, and excluded from every point's window (§1 Window: upload is
outside the system under test).

**Decision after the coarse pass** — ⟨which two refinement points, and the shape that placed them⟩

**#⟨n⟩** — ⟨deviation from the plan, anomaly, mid-run decision, why it was aborted⟩

### Close

- [ ] Saturation identified, or headroom confirmed at the top of the grid.
- [ ] Cost pass run at least 48 h after the last point, and re-run after the month closed if any figure moved.
- [ ] M12 decomposition present, or the per-component split declared not made.
- [ ] TEI peak replicas recorded at every point, and D23 computed or declared zero.
- [ ] M18 read at the highest-N point and compared against D30, or the comparison declared not made.
- [ ] Collection point count written back into `00-baseline` §2 Envelope.
- [ ] Every figure in §3 marked: unmarked · ᴰ · ᴿ · ᴱ.
- [ ] Outcome compared against Expected in Retro, inversion included.

---

## 3 · Results

**Finding** — ⟨one sentence: throughput plateaus at N=⟨⟩, unit cost bottoms at N=⟨⟩⟩ → report §3.3

### Matrix

| Run | N set | N reached | TEI peak | Docs/min | Wall time | Compute $ | TEI $ | Other $ | $/run | $/1M docs | Saturation signal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #01 | 4 | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #02 | 12 | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #03 | 24 | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #04 | ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |
| #05 | ⟨⟩ | ⟨⟩ | ⟨⟩ | ⟨⟩ ᴰ | | | ⟨⟩ ᴰ | | ⟨⟩ ᴰ | ⟨⟩ ᴰ | ⟨⟩ ᴿ |

`N reached` is M5, time-weighted mean with the peak in brackets. The curve is fitted against it,
not against `N set`. `TEI peak` is M9. `Compute $` is M10 and is billed rather than computed.
`TEI $` is D23, already net of the two-replica floor. `Other $` is M13 plus M14.

- **Knee** — N=⟨⟩, the last point with a meaningful docs/min gain. Threshold used ⟨⟩
- **Sweet spot** — N=⟨⟩, the minimum `$/1M docs`. A minimum landing on the lowest or highest N swept is not proven (`methodology.md` §7)
- **Waste boundary** — N=⟨⟩, where `$/run` rises substantially for under 10 % throughput
- **Gap cost** — ⟨⟩ extra per 1M docs paid at the knee rather than at the sweet spot → report §3.3
- **Reference value** — ⟨the pre-sweep default N⟩, and the Fargate equivalent D29
- **Condition boundary** — `00-baseline` §2 Envelope, plus packing density, bulk-drop arrival and the TEI trigger
- **Raw data** — `./data/frontier.csv`. No `plot-frontier.py` exists in `docs/report/scripts/` yet — chart by hand or write one before this execution closes

**Warm-up and unused capacity** — D26 at the lowest and highest N: ⟨⟩ → ⟨⟩ → report §3.4

**Marginal decomposition** — D27 at the sweet spot → report §4.2 · amortization D28 → §4.3

**Fargate equivalent** — D29 → report §4.4. It prices the worker pods at Fargate rates and is a
lower bound on what Fargate would actually cost. Three mechanisms move it upward and none move
it down: no Spot capacity type exists for Fargate on EKS, so the comparison runs against
On-Demand rates; requests are billed at the next step of a fixed vCPU and memory grid; and each
task gets its own microVM, so image pull is paid per worker rather than amortised across a node.
TEI is outside the comparison — it is a shared deployment on the serving pool either way.

**Sizing check** — D30 against M18: ⟨same order · differ by ⟨⟩⟩. A disagreement in magnitude is
a `00-baseline` revision, not a row here → K4.

### Saturation

**Tier 1 — ⟨component⟩ at N=⟨⟩, run #⟨n⟩**

- **Evidence** — M6 at the frozen limit, with R20 recorded at the point
- **Relieved by** — more workers at higher N. Cost of the next step ⟨$⟩ ᴰ

**Tier 2 — ⟨claimed only if a new ceiling was observed after Tier 1 was actually relieved⟩**

- **Evidence** — M15, M16 or M17, if they landed. A TEI ceiling here is a scaler ceiling rather than a hardware one, and M9 says which
- **Relieved by** — ⟨not attempted⟩

No third tier is claimed (`methodology.md` §8). A point with R20 empty contributes its cost row
and nothing here.

### Guardrails

- **`maxReplicaCount` = ⟨n⟩** — from the sweet spot in Matrix · `deploy/k8s/apps/⟨…⟩/scaledjob.yaml` → report §5
- **chunker `limits.memory` = ⟨⟩** — from M7 peak plus ⟨30⟩ %, valid only where M8 is zero · `deploy/k8s/apps/chunker` → report §5
- **indexer `limits.memory` = ⟨⟩** — from M7 peak plus ⟨30⟩ %, valid only where M8 is zero · `deploy/k8s/apps/indexer` → report §5
- **`consolidateAfter` = ⟨⟩** — from D26, only if the unused-capacity share proves material · `apps-compute` NodePool → report §5

Rows whose source number does not survive the runs are deleted, not left blank.

### Retro

- **Expectation** — ⟨held · inverted — what actually saturated, in the words that go into the report⟩
- **What should have been caught before the first run** — ⟨and which validity criterion should have caught it⟩
- **Concurrency delivered** — ⟨did M5 track N across the grid, or did the Spot pool cap the top⟩
- **TEI response** — ⟨did TEI scale at all under ingestion, and did its share of `$/run` grow with N⟩
- **Attribution** — ⟨did every point resolve to tagged CUR rows, and did split cost allocation return pods on every point⟩
- **Month-close revision** — ⟨did any cost figure move between the 48 h read and the closed month⟩
- **Back into the kit** — ⟨⟩
