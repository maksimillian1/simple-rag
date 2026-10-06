# Report tasks

Numbers flow one way: `00-baseline` → `01-ingestion` / `02-inference` → `report.md`. Work top to
bottom; a section only starts once the decisions it depends on are made. Size is a guess: S ≤ 30
min, M ≤ 2 h, L ≥ half a day. Work that needs a live cluster is in `docs/tech-debt.md`, not here.

## 0.4 · Charts → `report-kit` (first)

- [ ] 0.4.1 `docs/report/scripts/plot-charts.py` (799 lines, added 2026-09-29) moves into the
  package and is invoked as `report-kit charts`, the same move `figures.py` made in §0.6. Pin it in
  `requirements.txt` with the checker, and prove the two render identically before deleting the
  local copy · M
- [ ] 0.4.2 **This reopens D7**, which settled "remove for v1.0" and is why §3.2 and §3.6 now read
  "No chart in v1.0" and why 2.5 stripped every `frontier.csv` and `plot-*.py` reference from the
  execution documents. Re-decide D7 first: if charts ship, those places come back, and the CSVs the
  script's `SCHEMA` declares have to be written from `figures.yaml` rather than by hand · S

## Settled numbers (from `00-baseline` Floor)

| Figure | As built | Right-sized ᴱ |
| :--- | ---: | ---: |
| Block A (fixed + variable) | 323.71 (313.88 + 9.83) | 306.72 (296.89 + 9.83) |
| Block B (fixed + variable) | 553.83 (552.91 + 0.93) | 457.30 (456.38 + 0.93) |
| Block C | 877.54 | 764.02 |
| Serving pool idle rate | $0.3833/h on 09-04, $0.18754/h on 09-05 | — |
| Errors, recurring at rest (ArgoCD 65.85 + 9.05, EKS logs 100.95) | 175.85/month | — |
| Errors, already spent (PVCs 75.35, logs 2.26, standalone EBS 0.70) | 78.31 | — |
| `bedrock` endpoint, a defect inside the as-built floor | 26.28/month | removed |
| Cluster startup | 0.61 per launch | — |

Marginals are measured as of 2026-09-19: $0.024875/doc (D23 included) and $0.00375/1k queries
(campaign netted). Everything below is resolved by `figures.yaml`, so read it from the script
rather than from here:

| Derived | B as built | B right-sized |
| :--- | ---: | ---: |
| Docs/month where floor share = 50% | 22,265 | 18,384 |
| Queries/month where floor share = 50% | 147.8M | 122.1M |
| Floor share per 1k queries at 1000 req/s | $0.000211 | $0.000174 |
| Budget alarm, B × 1.4 | $775.37 | $640.22 |

## 0 · Decisions (they block the numbers)

| # | Decision | Options | Recommendation | Blocks |
| :--- | :--- | :--- | :--- | :--- |
| D1 | Which Block B is the headline | as built $553.83 ᴿ · right-sized $457.30 ᴱ · both | **settled: right-sized is the headline**, as built is the reference value it is judged against (ᴱ needs one, `methodology.md` §2). Every downstream figure that adds floor to a marginal carries both columns: §4.3 crossovers, floor share, budget alarm ($640.22). The serving line *rises* under right-sizing (Spot → On-Demand for HA) and that must be said, or the one line that goes up discredits the table. Precondition: the right-sized serving line assumes TEI requests 3/4, so tech-debt #4 stops being optional debt and becomes a condition of the headline number | 4.3–4.7 |
| D2 | How run costs net out the serving floor | (a) 09-04 rate $0.3833/h for every run: r050 net goes negative · (b) each run day's own resting serving inventory from CUR (09-05 serving ran on xlarge nodes, not 2xlarge) · (c) keep per-point figures gross for relative comparison, net only at campaign level | **settled: (b) + (c).** The marginal is measured and exists in one copy — floor does not enter it by definition (`methodology.md` §9), so subtracting a hypothetical right-sized floor from a real CUR bill would yield neither a measurement nor an estimate. (a) is out on its own: it subtracts a 2xlarge rate from a day that rested on xlarge. Per-point figures stay **gross** and are labelled gross; netting happens once, at campaign level, against 09-05's own inventory. No right-sized twin of the marginal: that configuration never ran. **Declared caveat:** the measured marginal also carries the as-built NodePool's instance selection — `apps-serving` admits xlarge/2xlarge/4xlarge, right-sizing pins `instance-size` to xlarge, so scale-out nodes under load would differ too; direction unknown, magnitude unmeasured | 2.1, 3.1, 3.2 |
| D3 | Re-run a cluster for the contention pass, real Bedrock, `D29`, `M15`–`M17`? | re-run · ship v1.0 with the gaps declared | **settled: ship.** Contention pass is dropped outright, not deferred — tech-debt #8 goes away as debt and becomes a declared scope boundary in Coverage (`methodology.md` §11): every query-path finding assumes an idle ingestion path. §5 row "Backfill concurrency during query hours" is deleted, not left blank (§10). Real Bedrock (#9) and chunker concurrency (#10) stay open — #9 is a different class of gap: ~$0.51/1k queries ᴱ is the largest number in the report and was never measured | 2.6, 3.5, 5.2 |
| D4 | `methodology.md` — **premise was wrong, it exists**: `report-kit@e0cd136`, `src/report_kit/templates/methodology.md`, 13 sections. All four citations resolve and are accurate (§7 "Sweep coarse to fine", §9 "Cost has exactly two terms") | vendor it to `docs/report/methodology.md` with a provenance header (source URL + commit + date) · link the citations to GitHub | **settled 2026-09-21: vendored.** `docs/report/methodology.md` (390 lines) and `docs/report/formats.md` (123) carry provenance headers naming the kit commit; all five cited sections (§2, §7, §9, §10, §11) resolve locally. 2.4 and 3.4 now only have to fix the relative paths in the citing files. Original reasoning: the citations must keep resolving to the text the report was written against, and an upstream edit would renumber the sections. (the `questionnaire.md` line calling it "a `methodology.md` that nobody wrote" went with that file) | 2.4, 3.4, 4.8 |
| D5 | `terraform/budgets.tf` (does not exist; no SNS or alerting exists in `terraform/` at all) | write it (~20 lines: `aws_sns_topic` + email subscription + `aws_budgets_budget`, 80% actual / 100% forecast) · delete the §5 row | **open.** "Keep the value, mark not enforced" is out: `methodology.md` §10 — a guardrail is a committable config value, and rows whose number cannot be committed are deleted, not left blank. Writing it is recommended: it is the only row in §5 not tied to one known lever, and `00-baseline` already found $175.82/month recurring plus $78.31 spent in exactly the class of drift a spend alarm catches. Threshold per D1: $640.22. **Settled: written up as `docs/tech-debt.md` #11**, given a fresh ID rather than renumbering the existing items. §5 now points there instead of at a file that does not exist | 4.7 |
| D6 | `maxReplicaCount` drift: ingestion live 10; TEI 30/30 at r1000 under a Spot quota of 256 vCPU | change config · record as is | **ingestion settled: recommend 20 ᴱ**, written into §5, §3.3 and `01-ingestion` Guardrails (which had said 50, against §5's 25 — three numbers, now one). Rationale: N=25's cap bound only at the peak, the run held a time-weighted mean of 19.5; no measurement separates 20 from 25, and the chunker's ~20 ceiling is corpus-driven. Live value raised 10 → 20 on both ScaledJobs (2026-09-19). **TEI settled: keep 30** — it carried ≥1000 req/s at steady-state p95 and ~0% error, so no Spot quota increase is requested; §5 row says so | 4.7 |
| D7 | Charts: `assets/*.svg` and `data/frontier.csv` do not exist, §3.2 and §3.6 point to them | build 2 charts from the Matrices (M) · remove the references (S) | remove for v1.0 | 2.5, 4.9 |
| D8 | `02-inference/data/*.point.md` | delete · keep | **settled 2026-09-28: keep.** The premise was wrong: they are not unfilled templates. Only the fields fed by the metrics export and the cost pass are blank; each file records the config commit with its dirty flag, the window, the generator-end instant, peak replicas, collection size at open, ceiling hits and guards breached. Three of the four generator-end instants existed nowhere else and are not recoverable, and that instant is exactly what a guard has to be read at — the r500 false failure came from reading one later. They are now in the Run ledger too, and the files stay as the run-time record | 3.4 |
| D9 | §1 Verdict | ship · ship with guardrails · do not ship | business call, last | 4.11 |
| D10 | What the published article is | copy `report.md` 1:1 · publish `report.md` itself · a derived file on the same registry | **settled 2026-10-03: a derived file, same registry.** `article.md` is the source of publication and `report.md` stays the authority on every claim; the article may compress, reorder and drop, never assert what the report does not. It is not a paste: it carries the same hidden marks, sits in `figures.yaml` `scan`, and `docs/report/scripts/render_article.py` strips them into `rendered/article.md`, rewrites repo-relative pointers into permalinks pinned to a commit, stamps the sha and refuses while `check` is dirty. That gate is the whole reason for a second file rather than a copy — a published number that no longer resolves is the failure this arrangement exists to prevent. The format differs on purpose: overlap is ~70%, and the other ~30% is prose no check covers, which is why §0.8 names section by section what is verbatim, what becomes a conclusion and what goes. Tables are decided one at a time — an existing chart, a new `charts/*.csv`, an image, or prose | 0.7, 0.8 |

## 0.6 · Settled 2026-09-19, applies everywhere

- **Query marginal: the broad definition.** Every row tagged to the serving pool and every NAT row counts; only what is floor by definition is subtracted (the 09-05 resting pair × 4 h + the NAT hourly fee = $0.9582). Campaign marginal $4.3706 → **$0.00375/1k queries**, against the published $0.00457. Cross-AZ transfer on serving nodes stays in: query traffic causes it. The narrow variant ($0.00331) stays in `figures.yaml` as the alternative, unused.
- **Arithmetic at full precision, rounded once at print.** This is what AWS does: 69% of this month's CUR rows carry 10 decimals, and rounding per row before summing would have overstated 2026-09 by $2.06 (1.4%).
- **Prose prints whole dollars** ($554, $457, $764). Cents stay in the §4.1 Floor table, where lines have to add up, and in rates and per-unit figures.
- **Numbers carry refs as of 2026-09-21.** Every figure has `ref` + `kind`: `FM` measured, `FR` recorded from an authority, `FD` derived, `FE` estimated. A published tariff is `R` even when read off our own CUR rows — its failure mode is a stale price card, not a bad window; what we actually paid (the Spot pair) stays `M`. The printed marker is computed, not authored: a formula with an estimate anywhere upstream prints ᴱ. `check-figures.py` is merged into `figures.py` (`check`, `validate`, `orphans`, `retype`, `renumber`) after proving identical output.
- **Marking done 2026-09-21.** 199 figures, **308 marked numbers**, 0 identity problems, retired values **none**, coverage 50/50. Marked: `report.md`, `00-baseline`, `01-ingestion`, `02-inference` (+ its `concepts.md`), `docs/tech-debt.md`. Two fixes were needed before any mark could be placed: the checker compared the printed digits against one stored precision, which rejected correct rate-card numbers (`$0.0952` against a figure rendering `0.10`) — it now compares at the precision the page chose, so `$554` and `553.83` both resolve to one figure; and the §4.2/§4.3 tables were still computed against the old Block B, so 26 figures were registered rather than recomputed by hand.
- **Both marking forms now parse.** The hidden form (`553.83<!--FD26-->`) always worked. The visible anchor `**$554** ᴿ (FD7)` did not: the checker allowed at most one character-class run before the `(`, so it matched only a bare `554 (FD7)` and skipped every anchor carrying bold or a trust marker — every anchor anyone would really write. Found by probing all four documented forms against the tool instead of reading the regex. Nothing in the report used the form, so no figure was ever wrongly verified; the contradiction was between `formats.md` and the checker.
- **Renumbering has one hazard.** Refs are tool-assigned, so reclassifying or appending is free, but **deleting** a figure shifts every later ref of that letter while the marks already in documents keep naming the old numbers. Deleting `query_per_1k_gross` moved 28 `FM` refs. Append, never insert; after a delete, re-run `check` and read the mark count. Written up in the kit's `formats.md`.
- **The checker comes from the package as of 2026-09-22.** `docs/report/scripts/figures.py` is deleted; the check is `report-kit figures check`, pinned to `v0.2` in `docs/report/requirements.txt`. The two were proved interchangeable before the swap — the package resolved this registry to the same 9 documents, 199 figures, 308 marks and 50/50 coverage at exit 0 — and v0.2 additionally skips fenced code blocks and inline code spans, which changed nothing here because no marked number lives inside one. The pin is a tag rather than a branch: these 308 marks were verified against one version of the resolver. The hook invokes it as `python3 -m report_kit.cli figures --path docs/report/figures.yaml check`, and both halves of that are load-bearing — a hook does not inherit an interactive shell's `PATH`, and the command finds a registry by walking *up* from the working directory, so from the repository root it would find nothing and exit 2 on every edit.
- **Registry baseline, 2026-10-03.** `check` now resolves **50 documents, 267 figures, 492 marked
numbers, coverage 126/126, retired values none**. The 199/308/50-50 counts in the 2026-09-21 bullet
above are that day's record and stay as written; this line is the one to quote. Two additions since:
group `steady_state` (b3) and the four remaining cells of report §3.4's unused-capacity column. The
count moves whenever a figure is added, so read it from the tool rather than from here.
- **The `bedrock` control-plane endpoint is an error, not a size.** It was provisioned and billed, so it stays inside the as-built floor and is listed in the `00-baseline` errors table; figure 2 removes it. That is the one line where the two figures differ for a reason other than sizing, and it widens the gap by $26.28/month (`docs/tech-debt.md` #12).

## 0.5 · Precondition for D2 (blocks 2.1, 3.1, 3.2)

- [x] 0.5.1 CUR bucket alive (2026-09-19): `BILLING_PERIOD=2026-09` parquet, 46,905 rows, refreshed 07:22 the same morning. September is still open, so K3's month-close re-read is still owed · S
- [x] 0.5.2 Done 2026-09-19, in `figures.yaml` group `campaign_0905`. The two days rested on different hardware: 09-04 on 2 × c7i-flex.2xlarge Spot ($0.37940/h, confirmed twice, hours 17 and 18), 09-05 on c5.xlarge + c6a.xlarge ($0.18480/h + $0.00274/h EBS = **$0.18754/h**, hour 12, the only clean rest between n10 draining and r050 starting at 12:58). The 09-05 floor is 49% of the 09-04 one, which is why subtracting $0.3833/h drove r050 negative. Hour 11 is not rest: n10 was still running and TEI held 3 replicas on 3 nodes · M
- [x] 0.5.3 The published campaign figures are reconciled rather than wrong: `serving_gross` $2.4505 = instances 1.9088 + EBS 0.0365 + **cross-AZ transfer tagged to the serving nodes 0.5052**; `nat` $2.8791 = NatGateway-Bytes 2.3610 + NatGateway-Hours 0.2080 + the NAT resource's own regional bytes 0.3093 (2.8783, a $0.0008 rounding gap). CUR has not been restated: the stray ingestion run still reconciles to the cent ($0.2127). The two stale fields in `campaign.cur-actual.json` are fixed and the file carries its own `revision_note`: `serving_floor_4h_usd` 0.9024 (4 h × the retired $0.2256/h) → 0.7502 = 4 × $0.18754 from 0.5.2, and `net_of_floor` 4.4272 → `marginal_total` 4.3706. **Data files are in coverage as of 2026-09-24**: `scan` carries `executions/*/data/*.json`, which took the check from 9 documents to 47 and surfaced six live stale numbers beyond the two above — the retired $0.2256/h as a field value in all five `inference-r*.cost-estimate.json`, and n50's pre-D23 $44,200 quoted in `ingestion-n10.cur-actual.json`. Per D2 the floor comes out once at campaign level, so the three per-point netting fields were removed rather than recomputed and D16 there is now the gross figure the report prints; each file records that in a `revision_note` and its original note is kept as written. The four deliberate was-then-now quotations are `allow` entries. `check` is clean at 47 documents, retired values none · S
- [x] 0.5.4 Dropped 2026-09-25, not fixed — it was a symptom. The retired scan matches a pattern as a literal substring, so `"41,624"` cannot match `41624.0` in JSON, and I filed that as a coverage hole. Under the data-file rule there is nothing there for it to match: a reading has no superseded version, only a result does, and results are not in data files any more. The one file it caught, `ingestion-n10.cur-actual.json`, was carrying results because it predated the rule; it is gone (0.5.6). The `executions/*/data/*.json` glob in `scan` stays as a guard against results reappearing there, which is the only thing it can usefully catch · S
- [x] 0.5.5 **Data files hold readings, not results** (2026-09-24). The rule is `figures.yaml` `meta.data_files`, with a one-bullet summary in `AGENTS.md` §7; `formats.md` and `methodology.md` are vendored, so it cannot live there. Why it was needed: eight of the twelve per-point cost files were hand-typed summaries, not tool output — `karpenter-cost-estimate.py --format json` emits a flat per-node array and its docstring says outright *“subtract 00-baseline's serving floor rate yourself — this script reports the gross node cost, not net”*, so every floor, net and per-1k field in those files was authored, and the per-node rows the totals rested on were never saved. Four ingestion points (n75, n100, n100-sticky, n125) had kept the real rows all along. **Rebuilt** all eight from each point's own Prometheus export (inference Q9, ingestion M2 = `kube_node_labels`, 15 s) re-priced from `describe-spot-price-history` at each node's `first_seen`: r050 $0.0747, r200 $0.1686, r300 $0.1769, r1000 $0.4992 and n25 $0.8750, n50 $0.9787 reproduce the live totals **to the cent**, which is the check that the method is the same one. Two came out different, both for a reason: r500 $0.3133 → **$0.3255** (the live run undercounted node `ip-10-0-11-199` by $0.0122 — kube-state-metrics emitted it as two series, one before its labels populated, and the script's timing dict kept the last, 0.0042 h instead of 0.1292 h; `m9_gross_r500`, `d16_gross_r500` 0.00117 → 0.00121 and the marks in `report.md` and `02-inference` follow, old values retired), and n10 $0.8032 → **$0.8767**, which settles that file's own “floor, not the real total” caveat: the five nodes EC2 could no longer identify carry their instance type, AZ and capacity type as node labels in the export. Not recoverable: `M11_serving_gross_usd` for n10/n25/n50 — `01-ingestion/data/series.txt` only ever exported apps-compute (M2), so no apps-serving series for those windows exists and the cluster is gone · M
- [x] 0.5.6 Closed 2026-09-25 by deleting the file, and the blocker I recorded here was my own mistake. `campaign.cur-actual.json` held thirteen numbers, twelve of them already figures in group `campaign_0905` and printed in the Campaign CUR table, each component with its own CUR slice named in its `source` (FM15 Spot instance-hours tagged apps-serving, FM18 `EUC1-NatGateway-Bytes`, and so on). So the provenance I called missing was there all along, per component; what I could not reproduce was the *totals*, using the exporter's defaults, which is not how they were built. The thirteenth, `baseline_other` 4.1969, is not registered and was not worth registering: $4.1969 over 4 h is $1.049/h against Block A's $0.443/h, so it is not the same set of lines as any floor figure and the file never recorded which slice it was — making the tempting comparison (the platform billed about what all five load points did) unusable without the very CUR pull this task was dropping. §4.3 already makes the floor-dominates point on measured figures. References rewritten: FM41's source and the `02-inference` pointer now name the table and the group, and the three `allow` entries for its `revision_note` are gone with it. Same treatment as `ingestion-n10.cur-actual.json`, and no data file carries an authored result any more · M

## 1 · 00-baseline (finish proofreading)

- [x] 1.1 Done 2026-09-26. No code changed: `nodepool.yaml` has carried `5m` on both pools since `cfa0ab7` (2026-09-03), raised from the `bafdc1f` plan values after a scheduling deadlock (postmortem 2026-09-02) — a day before the resting hour and before every run in this report, so `30 s` / `1 m` never applied to a measured figure. Four places, not two: the `00-baseline` freeze table's two rows now read `5 m` with their `consolidationPolicy` (`WhenEmpty` for `apps-compute`, `WhenEmptyOrUnderutilized` for `apps-serving`) and carry the date and reason of the change; `01-ingestion` 201 keeps its cause and drops the contrast — the export gap is 5m being short against the export, not a divergence from a frozen value; `01-ingestion` 661 keeps the deadlock and now dates it. §5's row is 4.7 · S
- [x] 1.2 Done 2026-09-26, and settled in code rather than described. `deploy/k8s/platform/tei-embeddings/deployment.yaml` is back to `cpu 3000m / 4000m`, so HEAD and the freeze agree again; tech-debt #4, which existed only to track that divergence, is deleted (numbering left alone — refs are identifiers and the Platform table already skips to 11). The freeze row now reads "the code carries this value; `1ef1f0a` raised it to `cpu 6 / 8` for `inference-r1000` alone and it was put back on 2026-09-26". The run that used 6/8 is flagged where a reader meets it: the run matrix's commit cell (`1ef1f0a` (dirty; **TEI 6/8**)), a line under the results matrix saying #06 is not the same configuration as #01-#05, and the same under §3.6's matrix in the report. §5's embedding-tier row no longer assumes the 6-core request: the Spot-quota ceiling is stated as depending on the per-pod request · S
- [x] 1.3 Done 2026-09-26. The claim confused two different things — which manifest an image tag resolves to, and which architecture the pod ran on — and `identity-2026-09-05.txt` records tags, not `sha256:` digests, so the manifests were never captured. What was recoverable is where each workload ran, from every `cost-estimate.json`'s per-node `nodepool` + `instance_type`: qdrant arm64 (r7g.large); **chunker and indexer arm64 only** — 91 node-instances, all `c7g`, the pool admits no other family; api and tei amd64 at rest and in all but two of the campaign's serving nodes, the exceptions one c8g.xlarge at `n125` and one c7g.4xlarge at `n75`, which `apps-serving` permits on purpose; platform amd64 (t3.large); Karpenter amd64 (Fargate). Those two arm64 nodes carried `api`: `tei-embeddings` pins `kubernetes.io/arch: amd64` (no arm64 manifest) while `api` does not, so the embedding tier is amd64 by construction and the API tier was not. **Config settled 2026-09-26**: the `apps-serving` NodePool is narrowed to `arch In [amd64]`, so one tier can no longer sit on hardware the other cannot use. The freeze table records the permissive value the campaign actually ran on, per 1.1's lesson, and the right-size row now says the tier stays amd64 because of TEI's image rather than because of sizing — the report moves the database line to Graviton and never said why serving could not follow. `arch` is the only architecture mention anywhere in the report set; `report.md` never raises it. Note the Envelope line was already right ("database and compute `arm64`") — the document contradicted itself · S
- [x] 1.4 Already fixed in `5a29ddb`, confirmed 2026-09-26: the Preflight line no longer says "Still open" — it now states that the setting is console-only, cannot be read back through `bcm-data-exports`' `TableConfigurations`, and that nothing here rests on it either way, since every per-pod split this report uses is tagged by AWS itself. The only remaining "still open" in the file is K3's month-close re-read, which is correctly open · S
- [x] 1.5 Done 2026-09-26, by re-pulling rather than labelling. **M2 and R5 now read the Floor's own resting hour**, 2026-09-04 18:00–19:00Z, exported to `00-baseline/data/idle-2026-09-04T1800.csv` (118 ordinary rows, $1.465973; the 134 split-cost children excluded as in the Floor). The 13:00 bootstrap hour is superseded and its CSV kept as the original capture. **M2 = 25.6%** ($0.3758642 / $1.465973) against 14.3% before, and the rise is a defect entering the numerator, not a tagging regression: the largest untagged line at rest is the CloudWatch vended-log charge $0.1382863 (FM8 × FR20, the FD34 error), which read $0.00000 in the bootstrap hour — net of it, 17.9%. **The 5% validity gate is gone**, because everything here that can carry a `feature` tag carries one and the remainder is AWS-managed flat charges; a threshold would measure AWS's tagging, not ours. The old definition ("denominator excludes the R5 lines", which describes 16.7%) never matched the printed number and is replaced by the stated denominator. **R5 is a mapping, not an allocation**: untagged money is Floor money seen through the tag column, so each line names the row that already prices it and takes that row's block — which corrected the file's old conclusion "Block A $0.21163, Block B $0.00", false twice over, since the untagged 50 GB gp3 rows are Qdrant PVCs (B) and their leftover twins are in the errors table. The "⟨A · B⟩" LB line settled **A** and FD19 moved with it, on the Gateway's ownership and scope rather than on Grafana's route — Block B $553.83 → $534.12, right-sized $457.30 → $437.59, budget alarm $640.22 → $612.63, both crossovers and the amortization tables following (worth its own §0 entry). `Karpenter $24.91/mo` and `Monitoring PVs still ᴰ` went with the rewrite. **Six figures registered**, group `attribution`: `idle_hour_total` FM56, `idle_hour_untagged` FM57, `eks_logs_hour` FD125, `untagged_share` FD126, `untagged_share_ex_logs` FD127, `feature_fill_rate` FD128 — they had been prose in ten places, which is the class of drift that produced this task, and `retired` can now point at them. Touched: Capture notes, Preflight 38/41/42, Metrics M1/M2/R5, Floor bullet, Raw data, Retro, `report.md` §4.1 and its Coverage row. **M1 signed** with the hour it was read over and with the cross-checks the pull produced (FM1, FM2's CUR input, FM3, FM8, FR7, FR12, FR18, FD6's inventory) — a cross-check, not a second derivation: monthly figures stay inventory × published rate × 730. One line where the two paths disagree is now written into §2: `KMS-Keys` bills $0.0013889/h because AWS prorated $1.00 across September's real 720 hours, so the 730 convention would read $1.0139; FD8 stays $1.00 from FR19. **Tooling:** `aws-cur-report-export.py` could not do this pull at all — its split-child guard used `pc.or_`, which propagates null, so every ordinary row was dropped and the tool returned an empty result; with `or_kleene` it reproduces both captured hours to the cent, which is likely why M1's original pull used `pyarrow` directly · M
- [x] 1.6 Done 2026-09-25. The approach is now stated once, as theses, in `methodology.md` §9 "Cost calculation approach (AWS)": CUR is the inventory and not the arithmetic, rows are summed only where the window is the answer, a monthly figure is inventory × published unit rate × 730, EBS is size × $/GB-month, variable lines are rest-hour usage projected, Spot carries one named hour's price into all 730, split-allocation child rows stay out of the parent total. `00-baseline` §2 now points at it and keeps only what is local: the bucket, the cost column's Savings-Plan note, region and currency, the rate card (incl. the Price List API rates § the PrivateLink per-GB pulled later), which resting hour each Spot figure rests on (Floor 09-04, campaign 09-05, half apart), and the reader — `pyarrow` directly, per M1, with the exporter's own prefix in `meta.cur`. Same pointer in `report.md` header and `meta.method`. The three wrong claims are gone: "a sum over its rows", "every other rate is in the CUR rows", "nothing about Spot is frozen" · S
- [x] 1.7 Done 2026-09-25. K3 is now "The monthly floor is one resting hour projected": CUR gives the inventory of one resting hour, a published unit rate times 730 gives the month (`methodology.md` §9), the multiplier is exact and what is assumed is that the hour is typical. The month-close re-read is **kept, narrowed**: once the period closes the inventory and the published rates cannot move, so the second read touches only Spot and the variable lines — which is also where the assumption bites, the two captured resting hours being half apart. Preflight line 52 and the Retro line already say the second read is still open and stay as they are · S
- [x] 1.8 [deleted] - `deploy/k8s/apps-applicationset.yaml`: comment says the loop is "cosmetic, no cost"; it is $74.86/month. Fix or delete the comment (AGENTS.md: no comments in config) · S
- [x] 1.9 Redefined 2026-09-29 into §0.7, not dropped. A full read of `00-baseline/index.md` is not what this document needs: its prose is evidence, the registry already enforces its numbers across 45 documents, and no reader reaches it except through a pointer in `report.md`. What is read instead is the sections `report.md` actually cites, listed in §0.7, with `humanizer` applied to those and not to the whole file · S · (`00-baseline/questionnaire.md` deleted 2026-09-19; its six problems live on as 1.1–1.8 here and as sections 2–4)

## 2 · 01-ingestion

- [x] 2.1 D23 measured 2026-09-19 for all five points, in `figures.yaml` group `d23`: each point owns one clock hour (n125→14, n75→15, n50→16, n25→17, n10→09-05 10-12), confirmed by matching CUR compute to the published per-point figures to the cent. Serving gross minus that day's rest rate gives $0.8161 / $0.5173 / $0.2935 / $0.0075 / $0.3107. NAT `Hours` is flat $0.0520 in every hour of both days, so it is floor, as assumed. **Still to write:** the Matrix `TEI $`, `$/run` and `$/1M docs` columns in `01-ingestion` and report §3.1 move with it, and the sweet spot becomes $24,875/1M docs · M
- [x] 2.2 Done 2026-09-28, re-read from CUR rather than patched. The node list did merge two pools into one pair: core is 2 × `t3.large` and the database is 2 × `r7g.large`, four nodes at a flat $0.4504/hour. The range was also wrong and the characterisation with it. Over the four full run hours (09-04 14:00–18:00Z) `baseline_other` is **$1.32–1.66/hour** against the stated ~$0.9–1.15, and only $0.7897 of it is fixed (the four nodes plus EKS control plane, Fargate, EBS, ELB, IPv4, KMS and the two Bedrock endpoints). The rest is not overhead: cross-AZ transfer runs $0.3362–0.8544 and scales with the run, and the CloudWatch vended-log defect adds up to $0.2376 once it starts billing at 15:00Z. The cross-check the task asked for holds on the fixed part alone: Floor C $1.2021/h minus serving $0.3833/h minus NAT $0.052/h = $0.7668/h against the measured $0.7897/h, the gap being EBS detail and rate × 730 against a measured hour · S
- [x] 2.3 Done 2026-09-25. Two of the four were already closed 2026-09-19 (TEI peak at every point, CUR-based D23). **M18 vs D30** — declared not made: `D30` was never defined in `00-baseline` or `report.md`, so there is nothing to compare against; `M18` stays in `./data/m18-qdrant-working-set.json`. **§3 marked** — done per `formats.md` Scope, with the M12 decomposition table as the one declared exception: its 35 per-app and `unused` cells are CUR `split_line_item_split_cost` / `split_line_item_unused_cost` read with pyarrow, provenance in `data/m12-eks-split.json` (`source`, `pulled`, `method`, `caveat`), and registering them would buy nothing while nothing quotes them. The **workload total** column is now registered and marked (`FM51`-`FM55`, group `m12_split`), because a total printed in prose is arithmetic · S
- [x] 2.4 Done 2026-09-28, in the same sweep as 3.4. All three — `index.md:18`, `index.md:534` (line 518 when the task was written) and `metrics.md:44` (D24) — now read `docs/report/methodology.md`, and the fourth in the same file, `index.md:461`, reads `docs/report/formats.md`. D4 called this fixing relative paths, but none of the citations was ever a markdown link: they were bare filenames in inline code, so nothing resolved or failed to resolve. The change is to one form of reference, from the repository root, readable at any depth · S
- [x] 2.5 Done 2026-09-28, removed rather than corrected. A file that was never written and a script that never existed do not belong in the report at all, so `frontier.csv`, `plot-frontier.py` and `plot-rate.py` are gone from every document, history included. Three places, one more than the task named: `01-ingestion` Raw data and `02-inference` Raw data both now list the files that do exist and close with "No chart in v1.0 (D7)" like `report.md` §3.2, and `01-ingestion/index.md:94` described the csv as a live pipeline step — it now names `⟨point⟩.cost-estimate.json`, where the netted figures actually land. Both Raw data lines also carried "chart it by hand before this execution closes", a standing instruction D7 had cancelled. The word `frontier` stays in `concepts.md` and `metrics.md`, where it names the curve rather than a file · S
- [x] 2.6 Questionnaire deleted 2026-09-19. `D29` stays declared-not-made (§4.4, tech-debt #10), `methodology.md` is D4, and the "N=10 rests on one run" caveat is already in the Matrix · S
- [x] 2.7 Redefined 2026-09-29 into §0.7, not dropped. A full read of `01-ingestion/index.md` is not what this document needs: its prose is evidence, the registry already enforces its numbers across 45 documents, and no reader reaches it except through a pointer in `report.md`. What is read instead is the sections `report.md` actually cites, listed in §0.7, with `humanizer` applied to those and not to the whole file · S

## 3 · 02-inference

- [x] 3.1 Done 2026-09-19 per D2 (c): the columns are now `Serving $ (gross)` = M9 and `$/1k queries (gross)` = M9 ÷ queries × 1000, in `figures.yaml` group `inference_points` (leaves from `data/*.cost-estimate.json`, D16 as formula). Gross D16 runs $0.00250 (r050) → $0.00088 (r1000), falling with rate as the resting pair is diluted; the old net values ($0.0159–$0.4151, $0.00054–$0.00090) are `retired`. The provisional paragraph is one sentence: M9 gross ᴰ, script, 2026-09-05, netted once at campaign level against $0.18754/h. Still flagged by the checker: report.md §3.6 carries the old net column (4.8). Added on 2026-09-21 after the two implementations were reconciled: a `Queries served` column, so the divisor D16 uses is visible in the table rather than only in `figures.yaml`; `campaign_queries` turned from a typed 1,166,534 into the sum of the five per-point counts; and a `naming` rule in `figures.yaml` meta, because the same number had been called `serving_gross_r050` locally and `m9_gross_r050` in the cloud branch. **Left alone on purpose:** `data/inference-r*.cost-estimate.json` still carry `M9_net_of_floor_usd` and `D16` computed at $0.2256/h, a rate retired twice; the fields the report actually uses from those files, `M9_serving_gross_usd` and `queries_served`, are sound · M
- [x] 3.2 Done 2026-09-21. The cross-check table now shows the netting step instead of implying it: gross total $5.3288, less the floor $0.9582 (09-05 resting pair × 4 h + the NAT hourly fee), marginal $4.3706 → **$0.00375/1k queries**. The published NAT total was $2.8791 against components summing to $2.8783; the components win, per the `meta.rule` that totals come from exact values. `query_per_1k_gross` (a typed leaf holding 0.00457) is deleted — it stated a gross number as if it were the marginal — and `campaign_gross_total` replaces it as a formula. Ratio against per-point D16 restated 1.8–5.2× → **1.5–4.3×** everywhere it appears. Fed into report §1, §3.6, §4.2, §4.3 · M
- [x] 3.3 Done. Matrix and Saturation already carried it after 1.2 (`02-inference` 406 and 538, plus the run ledger's commit cell and `report.md` §3.6), so what 3.3 asked for existed; confirmed 2026-09-26 and **one gap closed**: all four places bounded the divergence to the *shape* — latency and scaling — while the same Matrix prints #06's cost columns with no note. A 6-core request fits fewer pods per node, and #06 is the only point whose node mix is dominated by `4xlarge` (5 of 11 seen, against 12 of 17 at `xlarge` for #04), but `karpenter-cost-estimate.py` reconstructs node lifecycles rather than concurrency, so neither direction nor magnitude is readable. Declared in both Matrix notes in the same form as D2's instance-selection caveat, not guessed at · S
- [x] 3.4 Done 2026-09-28. **Citation:** none of the six references across the set was a markdown link, so nothing resolved or failed to resolve — they were bare filenames in inline code, identical in documents one and two levels down. All of them, plus the four in `report.md` and the two to `formats.md`, now read as `docs/report/methodology.md` from the repository root, which is unambiguous from any depth. **`point.md` per D8:** files kept, not deleted. D8 called them unfilled templates and they are not — only the export-fed and cost-pass fields are blank. Three of the four generator-end instants (r200 13:32:11Z, r300 14:37:53Z, r1000 15:05:34Z) lived only there, are unrecoverable, and are the instant an offered-rate guard must be read at, which is what the r500 false failure turned on. Carried into the Run ledger as a new column with a note on why it matters, and R13 rewritten to describe what the files actually hold · S
- [x] 3.5 Questionnaire deleted 2026-09-19. Contention is a declared scope boundary (D3), the Bedrock calibration stays open in `report.md` §1 Verdict and tech-debt #9, the `point.md` files are D8 · S
- [x] 3.6 Done 2026-09-22. `endpoint_processed_gb` (FR15) is **$0.01/GB** — Price List API, `AmazonVPC` / productFamily `VpcEndpoint` / usagetype `EUC1-VpcEndpoint-Bytes` / endpointType `PrivateLink`, first tier (up to 1 PB monthly; the 0.006 and 0.004 tiers are five orders of magnitude out of reach at 8.6 GB/month). Cross-check: the same family prices `EUC1-VpcEndpoint-Hours` at $0.012/h, which is `endpoint_eni_hour` (FR14) read independently from CUR — two sources agreeing on the neighbouring rate. The rate was pulled 13 days after the rest of the card, so it sits in `price-2026-09-09.json` as its own `privatelink` section carrying its own `pulled` date, and the file's top-level `note` now says the top-level date covers fargate and bedrock only. The whole `pending` chain resolved: `endpoint_breakeven_gb` 625.71 GB, **`endpoint_breakeven_queries` 72,648,746/month**, `endpoint_at_ref_queries` $26.37. All three print ᴱ, not ᴰ — `query_wire_bytes` carries an estimate upstream, and the marker is computed. §4.5's table cell `$26.28 ᴰ + pending ᴱ` became `$26.37 ᴱ` (FD54; the split into fixed plus processing is not printable without registering the processing component, which Rule 0 forbids doing in prose), and its "between 31.5M and 72.6M" range became the value — the old upper bound was this figure, so the range had already guessed the rate right. `D22` in `02-inference` moved blocked → active; `concepts.md` no longer calls it a range · S
- [x] 3.7 Done 2026-09-28, in two ADRs rather than by editing 0007: an ADR is a dated decision record, and rewriting the 2026-05-31 rationale would hide that the decision rested on a premise measurement later contradicted. 0007 keeps its text and gains a Status pointer. **`adr/0017-nat-gateway-topology.md`** carries what the investigation turned up on the way — NAT is not an egress convenience but cluster-critical (a node stays `NotReady` until Cilium's image is pulled from a public registry, so no egress means no node join anywhere), a NAT gateway is zonal and does not fail over, and the seven things it would take to remove the dependency cost more than a gateway per zone; hence `single_nat_gateway = false` in production, +$75.92/month, carried as a §5 guardrail at $83.22 including the two extra Elastic IPs, stated as sitting outside the right-sized floor rather than inside it. **`adr/0018-bedrock-egress-transport.md`** supersedes 0007 clause 2 and **removes both Bedrock endpoints**: the cost claim is false by 45× at the reference volume (break-even 54,854,311 queries against 1,000,000), and the privacy boundary is withdrawn as not worth $26.28/month here — and was never in effect anyway, both endpoints sitting in `eu-central-1` while the client calls `us-east-1`. Generation now egresses through NAT under TLS and IAM, and no VPC-perimeter claim survives anywhere in the repository. Floor follows: `block_b_fixed_rs` loses `vpc_endpoints` rather than only `vpc_endpoint_control_plane`, so right-sized B $437.59 → **$411.31**, C $764.02 → **$737.74**, budget alarm $612.63 → **$575.84**, both right-sized crossovers and the floor share with them · S
- [x] 3.8 Redefined 2026-09-29 into §0.7, not dropped. A full read of `02-inference/index.md` is not what this document needs: its prose is evidence, the registry already enforces its numbers across 45 documents, and no reader reaches it except through a pointer in `report.md`. What is read instead is the sections `report.md` actually cites, listed in §0.7, with `humanizer` applied to those and not to the whole file · S

## 4 · report.md (after 1–3)

- [x] 4.1 Done 2026-09-25, except `Changes`. Cost source now points at `methodology.md` §9 and `00-baseline` §2 instead of restating the method. `System under test` says outright that commit `1ef1f0a8` carries TEI at 6/8 and only `inference-r1000` ran on it, while every other point and the whole floor ran `cfa0ab79` at 3/4 (tech-debt #4). `Raw data` is the data directories and "No charts in v1.0 (D7)". **Open:** what the `Changes` line is meant to carry — say what it should say and it goes in · S
- [x] 4.2 Done 2026-09-25. The Idle floor row now states the method as one resting hour's inventory × unit rate × 730 (`methodology.md` §9) and says the projection carries that hour's prices, Spot included. New row above the untaggable one: errors found at rest, $175.85/month recurring and $78.31 already spent, outside every Floor figure as defects rather than sizing, with the `bedrock` control-plane endpoint named as the one exception that stays inside the as-built floor · S
- [x] 4.3 Done 2026-09-21. Floor line $553.83 / C $877.54; retrieval $0.00375 ᴰ; floor share $0.000211 ᴰ. The "~100x" / "~110x" disagreement is gone: both now print **~136×** from one figure, `generation_vs_retrieval`, so they cannot drift apart again · S
- [x] 4.4 Done 2026-09-25. §4.1 is now two tables: **As built** ᴰ (Block × fixed / variable at rest / total: B $552.91 + $0.93 = $553.83, A $313.88 + $9.83 = $323.71, C $866.79 + $10.76 = $877.54) and **Right-sized, same HA topology** ᴱ (B $456.38 + $0.93 = $457.30, A $296.89 + $9.83 = $306.72 — new figure FE16 — C $753.26 + $10.76 = $764.02), with the variable column stated as carried over unchanged and still marked ᴰ. Two tables rather than six columns so ᴰ and ᴱ never share a row. "⚠ provisional", "PVs still ᴰ" and "2 lines still variable/unrated" are gone, the last being simply false — both variable parts are figures (FD22, FD24). The lead-in states the method per `methodology.md` §9. "3 of 17 Floor lines" recounted to 3 of the 22 items the Floor prices, noting that S3, SQS and Qdrant snapshots share one row. Quantization no longer claims to make the database line small: it is why a `.large` node holds the collection at all, while the measured 379 MiB against r7g.large's 16 GB is exactly the unused memory the right-size removes. 14.3% left alone, it waits on 1.5 · M
- [x] 4.5 Done 2026-09-21. Embedding row is now `$3,256 − $766` as a formula, not a typed $2,490; the residual moved $19,665 → $19,790 because it is derived from the total rather than typed; shares recomputed 0.1 / 10.3 / 10.0 / 79.6% · S
- [x] 4.6 Done 2026-09-21, scripted as asked: all 16 amortization cells plus both crossovers are registered figures (`eff_per_doc_*`, `eff_per_query_*`, `floor_share_*`), so the tables are read from `figures.py` rather than recomputed by hand. Crossovers moved 17,250 → **22,265** docs and 93.4M → **147.8M** queries · S
- [x] 4.7 Done 2026-09-26. consolidateAfter row now reads live `apps-compute: 5m`, `WhenEmpty` — it had asserted `30s`, a value no measured run used (1.1); the fleet-wide §3.4 reasoning behind "not revised" is unchanged. Budget alarm is **$612.63**<!--FD56--> after the load balancer moved to Block A (1.5), with the as-built $747.77<!--FD57--> now printed beside it as D1 requires — it was registered but appeared nowhere. TEI ceiling note no longer assumes the 6-core request; the `budgets.tf` row points at tech-debt #11 (per D5); both `maxReplicaCount` rows rewritten (per D6) · S
- [x] 4.8 Done 2026-09-26. Of the three carries, one had landed, one did not apply, one was half done. **§3.1 `TEI $`** already carried the measured D23 (FM21-FM25, $0.82 / $0.52 / $0.29 / $0.01 / $0.31 for n125-n10, matching 2.1 to the cent), with `$/run` and `$/1M docs` moved with it and the sweet spot at $24,875. **§3.3's `methodology.md` citation** needed nothing: D4's relative-path fix is for the execution documents two levels down, while `report.md` sits in the same directory as the vendored file, so the bare name resolves — and §7 "Sweep coarse to fine" does carry the cited caveat ("minimum on a range boundary — not proven, no descending branch on one side"), which is what §3.3 leans on. **§3.6** carried 3.1's gross values but its column header was still authored by hand as `$/1k queries ᴿ` when FD78-FD82 are `kind: D`; the marker is computed, not authored (§0.6), and the checker cannot see a marker in a header. Fixed to `$/1k queries (gross) ᴰ`, matching `02-inference`'s name for the same column, and a paragraph under the table now says what gross means here and points at the campaign marginal $0.00375 — the omission mattered more than the marker, being the same confusion that forced `query_per_1k_gross` to be deleted in 3.2 · S
- [x] 4.9 Done 2026-09-25 per D7, references removed rather than charts built. §3.2 keeps its number (renumbering would break every citation of §3.3–§3.8) and is retitled "Ingestion — frontier": it now says there is no chart in v1.0 and that §3.1's Matrix is the frontier, plus the one thing the chart spec got wrong — `$/1M docs` rises with N instead of dipping to a minimum. §3.6's chart paragraph is replaced by one line pointing at its own Matrix. No `assets/` or `frontier.csv` reference is left in `report.md` · S
- [x] 4.10 Clean 2026-09-21: the grep returns nothing outside `figures.yaml`'s own `retired` list, and `figures.py check` reports `retired values: none` across all 9 scanned documents. **Data files covered 2026-09-24** (0.5.3): `scan` carries `executions/*/data/*.json`, and `check` is clean at 47 documents. What a substring scan still cannot see in a JSON number is 0.5.4 · S
- [x] 4.11 Settled 2026-09-28: **ship with guardrails**, the owner's call per D9. §1 now carries a "What the sweep settled" block above the Verdict: four findings, one each for ingestion, the query path and the baseline, and a fourth on the two paths having opposite operating points. The `Primary constraints` number bullet was dropped into them rather than kept alongside, since it restated the first two; nothing was lost, the constraint ladder itself living in §3.5 and its coverage rows. The Verdict names which §5 rows are conditions rather than suggestions (`single_nat_gateway = false`, the $575.84 budget alarm, the ingestion ceiling of 20) and which gap ships declared (E18, generation never measured, 136× the retrieval cost). Three figures were registered for it: `qdrant_cpu_peak` FM59, `qdrant_cpu_limit` FR27 and `qdrant_cpu_peak_share` FD137, plus `rightsize_fixed_saving` FD138. The Qdrant reading also corrected `02-inference` §3, which called 1.568 cores "nowhere near a limit" when the limit is 2 · S
- [x] 4.12 Folded into §0.7 on 2026-09-29 as 0.7.1, which is the same work with the method written down: read for sense, then `humanizer`, then the §1 findings aloud. It stays last, after 4.7, 4.8 and 4.11, all of which are now closed · S

---

## Proofread

### The order

- [ ] 0.7.0 §0.8's mapping, re-read against the report as it now stands. The 2026-10-03/04 batch
  changed almost every section the mapping calls *verbatim*, so it currently points at text that
  moved. Before the sense-read, and before any article prose exists · S
- [ ] 0.7.1 `report.md` in full: read for sense first, then the `humanizer` pass, then re-read the
  four §1 findings aloud. One file, and the only one a reader acts on · M
- [ ] 0.7.2 The cited sections of the execution documents only, listed below. `humanizer` on those
  sections, not on whole files: they hold 419 marked numbers whose printed digits must match the
  registry, and rewriting prose nobody reads is churn with a real chance of moving a mark · M
- [ ] 0.7.3 `check`, `validate` and `orphans` on every document afterwards. The mark count and
  coverage must come back unchanged; if they moved, the rewrite touched a number · S
- [ ] 0.7.4 `article.md` last, against §0.8's mapping: every row marked *verbatim* must still say
  what `report.md` says after the proofread, and every row marked *conclusion* must not have grown
  a claim of its own. Then `docs/report/scripts/render_article.py` — it runs `check` itself and refuses on a dirty
  registry, so a clean render is the sign-off · M

## 0.8 · What the article keeps, compresses and drops (D10)

Overlap is roughly 70%. The rows that say **verbatim** are the findings and the mechanisms: they
carry the article and must keep saying what `report.md` says. The rows that say **conclusion** are
where the format actually differs — an audit surface for a reader deciding whether to ship becomes
one or two sentences for a reader deciding whether to read. The **chart** column is what replaces a
table; charts come from `charts/*.csv` through `report-kit charts`, and the article and the slide
deck are where they are used.

| `report.md` | In the article | Table becomes |
| :--- | :--- | :--- |
| Header block | conclusion — one line: what was measured, where, when, and a link to the report | — |
| Coverage, 54 rows | conclusion — one paragraph: what is measured, what is declared, what is out of scope | dropped |
| §1 BLUF | verbatim, four figures | — |
| §1 What the sweep settled | verbatim — this is the article's spine | `tradeoff-jobs` for the fourth finding |
| §1 Verdict | conclusion — the three conditions, not the row-by-row reasoning | — |
| §2.1, §2.2 | conclusion — fixture, denominator, window | — |
| §2.3 | dropped, except the shared embedding tier and packing density | — |
| §3.1 | verbatim finding | matrix → `frontier-jobs` plus three lines |
| §3.2 | folded into §3.1 | — |
| §3.3 | verbatim | table → prose |
| §3.4 | verbatim — the mechanism the report was written to test | `split-jobs` |
| §3.5 | verbatim — the ceiling is in the code, which is the article's best line | — |
| §3.6 | conclusion plus the hold (b3) | matrix → `frontier-api` |
| §3.7 | verbatim, qualification and asterisk included | — |
| §3.8 | conclusion — one sentence naming the scope boundary | dropped |
| §4.1 | verbatim, hidden lines included (NAT, endpoints, quantization) | two tables → `floor-blocks` plus one image |
| §4.2 | verbatim | tables → image |
| §4.3 | conclusion — the crossovers and what they mean | both tables → `amortization-docs`, `amortization-queries` |
| §4.4 | verbatim — both conditional alternatives | tables → prose |
| §5, 16 rows | conclusion — the three committable conditions, one sentence for the rest | dropped |

Two things this mapping exists to catch. A later edit to `report.md` has a named place to check:
if it touches a **verbatim** row, the article moves with it. And a **conclusion** row is where a
claim can quietly appear that no execution file supports — the registry will not see it, because it
is prose.

---

### What `report.md` cites, and therefore what gets read

Everything else in the three execution files is evidence: it is reachable, dated and checked, and
no reader arrives at it except through one of these pointers.

| Target | Where it lives | Cited |
| :--- | :--- | ---: |
| `00-baseline` §2 Results — Cost basis, Envelope, Floor, Right-sized floor | `index.md:66–201` | 10× |
| `00-baseline` §1 Preflight, and `R5` | `index.md:13–65` | 2× |
| `01-ingestion` §3 Results — Matrix, M12, Saturation, Guardrails | `index.md:484–686` | 3× + `D23` `D25` `D26` `M10` `M12` |
| `01-ingestion` §1 Plan and §2 Journal — Notes, and `M6` `M7` `M15` `D29` | `index.md:12–467` | 3× + 7 refs |
| `02-inference` §3 Results — Matrix, Contention pass, Saturation | `index.md:383–565` | 5× + `D15` `D16` `M6` `M7` |
| `02-inference` §1 Plan — `E18`, `K4`, `R14` | `index.md:12–142` | 7× |
| `02-inference` §2 Journal — Notes | `index.md:143–382` | 1× |

`E18` and `K4` carry the report's largest estimate and the assumptions under it, so they are read
with the care given to §4.5, not as evidence.

---

### Weak points to check before the read (flagged 2026-10-01)

A review of `report.md` against the three execution files, `figures.yaml`, `tech-debt.md` and the
decisions above, plus what the humanizer pass left standing inside the execution files. Each line is "where → what is wrong", in severity order inside each group. **†** the
execution file is right and only `report.md` is wrong; **‡** the problem sits inside an execution
file.

Decisions live on a board rather than in this list: **Red Pencil** —
`https://claude.ai/artifact/TFJZzPveHpxNNJuUiyVj2i`. It holds the chosen resolution per item, and
any edited wording of it, in the artifact's own store: collection `decisions`, one document per id
with `choice`, `texts` and `resolved`. The board is the working surface, this list is the record.
**A resolved item leaves the board and is ticked here** — `- [x]` plus
`· решено <date>: <what was done>` at the end of its line. Resolved so far: **b3**; the 2026-10-03 batch — b1, a1, a2, b2, b4, b5, b6, b7, b9, b13; and **b16** on 2026-10-04.

### Порядок перед вычиткой · оценки 2026-10-04

⟨N⟩ у каждого открытого пункта — важность по одному вопросу: **испортит ли это вычитку, если не
решить заранее.** Не «насколько неверно», а «потеряется ли работа». Для калибровки: из тринадцати
закрытых на 8-10 тянут b3, b1, b9, b4, a1/a2, b16; b2, b13, b7 и a10 были 6-7; b5 и b6 — 4-5, они
проехали прицепом к соседям.

**Сначала, до чтения.** Каждый либо удаляет текст, который иначе будешь вычитывать, либо подаёт в
проход неверное число.

- **a3 ⟨9⟩** — решение, а не правка: если `n100` входит в матрицу, §3.1-§3.4 переписываются поверх
  сегодняшних a1/a2
- **b11 + b12 ⟨8⟩** — два абзаца §3.5 удаляются целиком, а §3.5 в мэппинге помечен *verbatim*
- **b18 ⟨8⟩** — восемь строк §5 либо уходят, либо остаются; §5 в статье сжимается до выводов
- **a8 ⟨7⟩** — дефект инструмента, а не отчёта: «Settled numbers» подсказывает снятые числа тому,
  кто читает
- **a9, a5 ⟨7⟩** — минута каждая, но кормят §4.2/§4.3 и штамп рендера

**По ходу чтения, один проход.** a12 ⟨7⟩, затем b8, a15, b17, b21, b22, b15 ⟨6⟩ — фактические,
ловятся на своём абзаце. b14, b19, b20, b10, a7, a16 ⟨5⟩ и a4, a6, a11, a14 ⟨4⟩ — формулировки.
Одно решение внутри группы: **a7** закрывается одной строкой «D1 говорит right-sized, статья ведёт
as-built, потому что это то, что реально заплачено».

**После публикации ⟨2-3⟩.** a13, a17-a28 — внутри execution-файлов, читателю статьи невидимы, а его
ссылки это permalink'и на коммит. b23 — правило для кита. b24 — нужна выгрузка CUR, и это
единственное, что держит `orphans` непустым.

**Чего в списке нет и что важнее всего ⟨9⟩.** Мэппинг §0.8 написан против старого отчёта: за
2026-10-03/04 изменились §1, §2.3, §3.1, §3.2, §3.3, §3.4, §3.6, §3.7, §4.2 и §5 — почти каждая
строка, помеченная *verbatim*. Перечитать до того, как появится проза статьи, иначе он указывает на
текст, которого нет: это 0.7.0 в §0.7. И отдельно: отчёт правили десятком заходов, §3.7 переписан
трижды, §3.3 дважды, целиком его после этого никто не читал — sense-read нужен сам по себе,
независимо от списка.

#### a) Несостыковки — two places say different things

- [x] a1 **§3.4 denies the shape §3.1 prints.** "`$/1M docs` rises monotonically with N, N=10
  through 125, no U-shape" against 44,707 → 24,875 → 44,335 → 61,573 → 88,161, a V with its
  minimum at N=25. §1 and §3.2 repeat the wording. Defensible: "rises monotonically from N=25 upward"
  · **решено 2026-10-03**: "rises monotonically from N=25 upward; N=10 is higher still" in §1, §3.2 and §3.4; the "no U-shape" claim is gone.
- [x] a2 **§3.1 and §3.3 disagree on N=10.** §3.1: "its real cost is trusted". §3.3: "no N below it
  has a trustworthy cost read" and "the true floor may sit below N=25, untested", though N=10 was
  tested at a higher cost. † `01-ingestion` Sweet spot: "N=10 could already be past it and rising"
  · **решено 2026-10-03**: §3.3 rewritten: N=25 is a measured local minimum, N=10's cost read is genuine and higher, and what stays untested is the gap between 10 and 25 rather than everything below 25. §1 follows.
- [ ] a3 ⟨9⟩ **N=100 is in neither the matrix nor the excluded list.** Ledger #04 `ingestion-n100` is a
  clean post-fix point (plus #03 `n50-test`, #04a `n100-sticky`); §3.1 excludes only N=4/12/24 and
  175, so the reader sees five runs of eight and a1's claim spans a hole at 100. Check
  `D24 ≈ $1.76/run` against the Matrix's `$/run` first
- [ ] a4 ⟨4⟩ **The planned grid is cited three ways.** §3.1 "4/12/24/refine/refine" against
  `01-ingestion` Plan: {4,24,50,100,125,175}, revised from {4,8,12,16,20,24}, swept as {4,50,175}
  plus refinements
- [ ] a5 ⟨7⟩ **The report's date precedes its content.** Header "v1.0 · 2026-09-09"; the text carries
  the 2026-09-26 Gateway decision, `ADR-0018`, `vpc.tf` "as of 2026-09-28" and §5's 2026-09-19
  changes
- [ ] a6 ⟨4⟩ **Dead citations.** The header cites `tech-debt.md` #4, deleted by 1.2; §4.1 cites "§4.5",
  which doesn't exist (4.1–4.4), and `tech-debt.md` #12 cites it back
- [ ] a7 ⟨5⟩ **§1 leads with the as-built floor, against D1.** It gives $534.12 and $877.54 and no
  right-sized figure
- [ ] a8 ⟨7⟩ **"Settled numbers" at the top of this file is stale**: B 553.83/457.30, A 323.71, C
  764.02, crossovers 22,265 / 147.8M, floor share 0.000211, alarm 775.37/640.22, against the
  report's 534.12 / 411.31 / 343.42 / 737.74 / 21,472 / 142.5M / 0.000203 / 747.77 / 575.84. Same
  for D1's and D5's thresholds and D6's text. Fix or delete before the read, or it seeds wrong
  corrections
- [ ] a9 ⟨7⟩ **The query crossover prints twice.** §4.2 "~148M queries/month" (the retired 147.8M)
  against §4.3's 142,547,228
- [x] a10 **A month is 730 h and 720 h.** Done 2026-10-03: always 730. `seconds_per_month` (FR28) is
  now `hours_per_month * 3600`, and §4.3's rates are registered and marked (FD146–FD151): crossover
  55 → 54 req/s, 500M 193 → 190, a billion 386 → 381
- [ ] a11 ⟨4⟩ **"Six points running"** for 84,018 (§2.1) against `01-ingestion` "the seventh time" and
  `00-baseline` Topology, `n50-test` through `n10` (eight) †
- [ ] a12 ⟨7⟩ **Qdrant node count.** §3.7 "one dedicated node", §4.1 "Qdrant node + gp3", against
  `00-baseline`: 2 × r7g.large, one shard replicated across both †
- [ ] a13 ⟨3⟩ **Waste boundary.** §3.1, §3.3 and the `01-ingestion` Matrix say "+39% cost"; the
  `01-ingestion` Waste boundary line says "rises 35%". 6.16/4.43 = +39%, so that line is stale ‡
- [ ] a14 ⟨4⟩ **$1.4787 carries two markers**: ᴿ in §3.4's table, unmarked (FM50) in §4.4
- [ ] a15 ⟨6⟩ **Printed tables don't add** (rounding at print per §0.6, which the report never states):
  533.20 + 0.93 = 534.13 printed 534.12; 410.39 + 0.93 = 411.32 printed 411.31; 410.39 + 316.60 =
  726.99 printed 726.98; §3.1 N=25 1.09 + 0.01 + 1.38 = 2.48 printed 2.49. One footnote covers all four
- [ ] a16 ⟨5⟩ **Coverage's Status column mixes four kinds of value** (a status, a trust marker, a whole
  method paragraph on the Idle-floor row), and "Since" means "measured since" on some rows and
  "targeted for" on the v1.1 ones
- [ ] a17 ⟨2⟩ **`00-baseline` untagged lines.** Retro: "8 non-zero untagged lines, $0.21163"; R5 now
  has 11 combos and $0.3758642 ‡
- [ ] a18 ⟨2⟩ **`00-baseline` right-sized endpoints.** The lead-in removes only the `bedrock` endpoint;
  the table removes both (`ADR-0018`) ‡
- [ ] a19 ⟨2⟩ **`00-baseline` Retro cites "the worry in M2's own notes"**, which M2's notes don't
  contain ‡
- [ ] a20 ⟨3⟩ **`01-ingestion` N=25 NAT**: $1.44 in prose, $1.38 in the Matrix's `Other $` ‡
- [ ] a21 ⟨3⟩ **`01-ingestion` "monotonic downward"** (ledger #09, Retro), where cost rises with N ‡
- [ ] a22 ⟨2⟩ **`01-ingestion` Retro: "`D23` is still the unresolved rough estimate"**; Close says it
  was measured 2026-09-19 ‡
- [ ] a23 ⟨3⟩ **`02-inference` r050 served rate.** Notes keep it flagged "until the tighter re-read,
  before it is used in §3's Matrix"; the Matrix already uses it ‡
- [ ] a24 ⟨2⟩ **`02-inference` #03 pod timing.** "Started at `13:38:52`, after the window closed at
  `13:39:24`", but 13:38:52 is the earlier time ‡
- [ ] a25 ⟨3⟩ **`02-inference` #05 narrows the knee to (300, 500)**; #04 and the Finding say 500 is
  sustainable and there is no ceiling ‡
- [ ] a26 ⟨2⟩ **`02-inference` contention pass at N=50**; the `01-ingestion` guardrail is now 20 ‡
- [ ] a27 ⟨3⟩ **`02-inference` TEI `maxReplicaCount` row** derives ~35-40 replicas from 6 cores per pod;
  TEI is back at 3/4 since 2026-09-26 (4.7 fixed this in the report only) ‡
- [ ] a28 ⟨2⟩ Minor: `02-inference` Safeguards still holds the template placeholders `⟨wall time⟩ · ⟨$⟩` ‡

#### b) Нелогичности — the claim does not follow from the data

- [x] b1 **The retrieval-latency claim fails its arithmetic, on a disclaimed instrument.** §3.7:
  retrieval-only "would sit well inside 200ms", but 2425 − 2000 = 425 ms. p50 1672 ms sits *below*
  the 2000 ms stub, which `02-inference` calls impossible for a constant sleep (Envoy buckets jump
  1000 → 2500 ms, so p50/p95 are directional only). That caveat never reaches `report.md`, yet §1's
  "missed by ~2225ms, almost all of which is the stub" rests on it †
  · **решено 2026-10-03**: §3.7's Reference value rewritten around the generator's own per-request durations: successful responses at r050/r300 have p95 2.04s/2.06s, median 2.03s, so retrieval plus the internet round trip is ~40-60ms once the 2000ms stub comes off — measured, where "well inside 200ms" had been asserted. Also records that Envoy reads ~380ms higher than k6 at the same point (buckets 1000 → 2500), which is where §3.6's 2425ms comes from. §1 follows.
- [x] b2 **The knee threshold contradicts the knee.** 10% gain per step gives 50, but 75 → 125 is
  2.33 → 2.60 = +11.6%. `01-ingestion` has the same gap, and also says "no saturation point exists
  to name as a knee", then names one
  · **решено 2026-10-03**: The definition changes, and both numbers are printed: the stated 10%-per-step rule selects N=125, the top of the swept range, because the gains are not monotone (+113 / +40 / +2.6 / +11.6%), so the knee is **not identified** — a rule landing on the edge of the range has found no bend. N=50 keeps its role as the ceiling for a hurry and as what the Gap cost is measured against, under its own name. Same in `01-ingestion`'s Knee line.
- [x] b3 **≥1000 req/s comes from a row the report's own rule excludes.** §3.6 excludes rows where
  served falls short of offered; r1000 served 828.3 (83%), r500 80%. "Once converged" is the way
  out, but only a converged p95 and error rate are published, no converged *served* rate
  · **решено 2026-10-03**: re-read both points sample by sample from their own `Q1`/`Q2` exports
  and from the k6 logs, which had never been read (M1 takes served rate from Prometheus only).
  Each point *holds* its offered rate at the p95 floor for about 1m45s — `r1000` 998–1,001 req/s
  at 0.02% errors (14:57:16–14:59:01Z), `r500` 499–501 req/s at 0.25% (14:00:51–14:01:51Z) — while
  the phase around the hold misses `D15`'s 0.1% bound (0.28% / 955 req/s and 0.49% / 457 req/s).
  Both window averages also carry the generator's own shortfall: 30,985 of 600,000 scheduled
  iterations dropped at `r1000` and 32,045 of 300,000 at `r500`, VU pool pinned at its ceiling,
  plus a three-minute stall inside `r1000` that the Notes had written up as the system scaling in.
  `report.md` declares the qualified figure once (§1 BLUF, §3.7) and carries `*` at every later
  use; `02-inference`'s Finding, Matrix note, both phase tables, #04/#06 Notes and the Retro
  follow. 17 figures registered as `figures.yaml` group `steady_state`; `check` clean at 263
  figures / 488 marks / 122-122 coverage
- [x] b4 **§4.2 decomposes a cash total with apportioned shares.** Reframed 2026-10-03, and the
  earlier reading of it ("33× discrepancy, may move the headline") was wrong: the rows sum to
  $24,875 by construction, so the headline cannot move. What the two numbers are: §3.1's `TEI $`
  = $0.0075/run is **cash** (serving-pool node bill for the hour minus the day's resting rate — at
  N=25 TEI went 2 → 4 replicas on the pair of nodes already running, so almost no new money left
  the account), while §4.2's $3,256 − $766 = $0.249/run is **apportionment** (AWS split cost
  allocation dividing those same nodes' bill among their pods by request; confirmed against
  `m12-eks-split.json` n25: tei-embeddings 0.3256, indexer 0.2574, chunker 0.0021). Apportionment
  moves money between pods on a node whose bill did not change, so the 33× is expected and both
  figures are legitimate. The defect is that they share a table: the total is cash, the components
  are apportionment, and the residual $19,790 — derived as total minus the three — silently absorbs
  the difference, so the embedding row takes $2,490 of the headline where ~$75 of cash is
  attributable. About 10% of $24,875 is attributed to the wrong place, and Coverage calls the §4.2
  row `D23`, which is the other method
  · **решено 2026-10-03**: §4.2 now states the two currencies: the total is cash (`cur_marginal` + D23), the three component rows are split-cost apportionment that moves money between pods on a node whose bill did not change, and the residual carries the difference — with N=25's $0.01/run cash against its $0.249/run apportioned share as the worked example. Coverage's row repointed: cash reading and apportioned reading named separately.
- [x] b5 **§2.3 says no run measured a ceiling** ("set out of reach"); §5 says the TEI cap of 30
  "was fully used at r1000 with zero margin"
  · **решено 2026-10-03**: §2.3 now says the ingestion ceilings stayed out of reach while the embedding tier reached its 30 at r1000, and keeps the point as the declared exception to `02-inference`'s exclusion rule, because the tier converged there and held the rate at ~0% errors. §5's embedding row points at §2.3.
- [x] b6 **"4 components … sum correctly" (§4.2)** is three plus a residual: the fourth ($19,790)
  is the total minus the other three, and the same row says it doesn't reconcile with the Matrix
  · **решено 2026-10-03**: §4.2: "three components from the split-cost source plus a residual derived from the total".
- [x] b7 **Defects-beat-sizing is computed with a defect inside the sizing.** §1: $175.85/month
  against "$139.80 ᴱ saved by right-sizing every line". Per `tech-debt` #5 sizing alone is
  $866.79 → $779.54 = $87.25; the other $52.56 is the two Bedrock endpoints, defects per §0.6 and
  the errors table. The finding gets *stronger* with the right number
  · **решено 2026-10-03**: §1 keeps $139.80 and states that $52.56 of it is the two Bedrock endpoints, a defect rather than a size, so sizing alone accounts for $87.25.
- [ ] b8 ⟨6⟩ **The quantization argument runs at 12× the collection.** §4.1 reasons at 1M points
  (0.384 GB against 1.536 GB) for why "a `.large` node holds the collection at all"; the collection
  is 84,018 points, which any node holds. The real reason for the class is the 2-vCPU / 1.568-core
  peak, already in the section
- [x] b9 **"No constraint found" against "a real, momentary saturation".** §3.7 against
  `02-inference` Saturation (TEI at 87–97.5% of limit). The no-ceiling proof also rests on r1000,
  the only point at `cpu 6 / 8`; the five `3 / 4` rows publish no TEI CPU peak
  · **решено 2026-10-03**: §3.7 narrowed to "no *sustained* ceiling": TEI's 87-97.5% during r1000's ramp is named as the momentary saturation `02-inference` calls it, and the claim is scoped to the `cpu 6 / 8` request, with the five `3 / 4` rows publishing no TEI CPU peak.
- [ ] b10 ⟨5⟩ **Two superlatives.** §1 Verdict: generation (`E18`) is "the largest number in the query
  path"; §3.8: contention is "the largest open item in this report", while the Verdict calls
  contention a scope boundary "and not a gap"
- [ ] b11 ⟨8⟩ **§3.5 carries plan text for a sweep that never ran**: the N=4 → N=24 chunker argument
  ("why the sweep runs to 24 rather than stopping at 12") and "If the embedding tier appears as
  Tier 2 …", in future tense, with no Tier 2 observed and 4/12/24 never run (a4)
- [ ] b12 ⟨8⟩ **§3.5's Tier 2 precondition names the wrong component.** Tier 1 is the indexer's
  sequential loop; the Tier 2 bullet reasons from "the chunker was never relieved by a resource fix"
- [x] b13 **N, `maxReplicaCount` and observed concurrency don't reconcile.** The live cap was 10
  through every run (20 from 2026-09-19), yet N ran to 125 with the indexer "at its full 125/125
  ceiling" and the chunker at ~20. Say once what N sets and what the cap limits, or §5's guardrail
  of 20 reads as a value the sweep already passed
  · **решено 2026-10-03**: §3.1 defines N once — the `maxReplicaCount` set on both ScaledJobs before the run, recorded by `run-ingestion-point.py --n`, a cap and not an observed concurrency — and reconciles the three numbers: the indexer tracked N exactly, the chunker peaked at ~20 at every N because the corpus cannot keep more busy, the cap bound on it only at N=10, and the committed value between runs was 10. §5's guardrail row says why 20 sits below four of the five swept Ns.
- [ ] b14 ⟨5⟩ **§3.1 claims a second docs/min measurement** ("the derivative of queue depth … catches a
  run that stalled"), but §3 has no such result and §3.4's warm-up and tail columns are "not
  captured". Cite it or demote it to method
- [ ] b15 ⟨6⟩ **§3.4 retracts itself.** "Split cost allocation reports them directly", then the next
  paragraph: the number is fleet-wide and can't be separated from platform idle
- [x] b16 **Four rows share p95 = 2425 ms to the millisecond** (r200, r300, r500 and r1000
  converged) without remark; against Envoy's 1000 → 2500 gap that is one interpolation artifact
  · **решено 2026-10-04**: двумя колонками, а не оговоркой. Пустая колонка `p99` заменена на
  `p95 ms (k6)`, Envoy-колонка подписана как Envoy — в §3.6 и в матрице `02-inference`. k6 по
  успешным ответам: 2040 / 2150 / 2060 ms на r050 / r200 / r300 и 10,630 / 4,730 за весь прогон
  на r500 / r1000, где сводка k6 включает минуты масштабирования и hold из неё не вырезать.
  Абзац под каждой таблицей показывает арифметику `1000 + 0.95 × 1500 = 2425`, из-за которой
  четыре рейта совпадают, отмечает, что та же интерполяция кладёт p50 ниже стаба, и что k6 меряет
  снаружи VPC — то есть должен читать выше, а читает на 300–400 ms ниже
- [ ] b17 ⟨6⟩ **§4.2's query table says "at the sustained rate"** for a campaign-wide marginal over
  50–1000 req/s, and §4.3 then puts the low rows outside the measured regime
- [ ] b18 ⟨8⟩ **§5 keeps rows with no committable value** (eight "not set" / "not revised"), against D5
  and `methodology.md` §10, and keeps "Backfill concurrency during query hours", which D3 deleted
- [ ] b19 ⟨5⟩ **A condition nothing enforces.** §1 makes the $575.84 alarm one of three conditions; §5
  says `terraform/budgets.tf` doesn't exist. Make the condition "write it" (`tech-debt` #11) or drop it
- [ ] b20 ⟨5⟩ **Spurious precision on estimated crossovers**: 142,547,228 and 54,854,311 queries from
  three-significant-figure inputs, the second called "an order of magnitude" in its own paragraph
- [ ] b21 ⟨6⟩ **§5 citations that lead nowhere.** "Max input file size | §3.5 · ADR-0001" (§3.5 has no
  file-size content); "Chunks per SQS message | §4.2 SQS line" (§4.2 has no SQS line; SQS is in the
  residual row)
- [ ] b23 ⟨3⟩ **The generator's own counters are published nowhere, and on two points they are
  double-digit.** `dropped_iterations` — iterations k6 could not start because no VU was free —
  runs 56 / 377 / 0 / **32,045** / **30,985** across r050-r1000, i.e. 10.7% of what was scheduled
  at r500 and 5.2% at r1000, with the pool pinned at its ceiling both times. `02-inference` M1
  takes served rate from Prometheus and never from k6's output, which is right for the system's
  view and leaves the one instrument that says when the *generator* stopped being open-loop
  unread. b3 put the two numbers into §3.6 and the Matrix note; what is still missing is the rule:
  a point's close should print `dropped_iterations`, peak VU occupancy against `maxVUs` and k6's
  progress cadence beside the Prometheus figures, and a point whose drop share is over a few
  percent is a generator reading, not a system one. Written into `02-inference`'s Retro
  ("Back into the kit", item 3) on 2026-10-03; it belongs in the kit's point template, not only
  in this campaign's retro · S
- [ ] b24 ⟨3⟩ **§3.1's `Compute $` and `Other $` columns have no saved decomposition.** They split
  `cur_marginal_nXX`, which is registered, but the split itself exists only as printed cents —
  `orphans` reports all eight cells and nothing in `executions/01-ingestion/data/` carries them,
  so they cannot be registered without inventing precision. One CUR pull over the five point hours
  settles it, and K3's month-close re-read is owed anyway now that 2026-09 has closed. Until then
  the two columns are the only unregistered numbers left in `report.md` · S
- [ ] b22 ⟨6⟩ Minor: "Article 1" (§4.1) is never identified; the header's "1000 is not a swept maximum"
  means *not a proven ceiling* (1000 is the top rate swept); §1 marks the sustained rate ᴿ where
  §4.3's "`api` held 2 replicas to ~300 requests a second"
  against 3 at r300 in the matrix — the one item here that is a wrong number rather than a copy-edit;
  §4's formula adds the two denominators the lead-in says are never mixed. (The ᴿ marker on the
  sustained rate went with b3's rewrite of that bullet, 2026-10-03.)
