# Report tasks

Numbers flow one way: `00-baseline` → `01-ingestion` / `02-inference` → `report.md`. Work top to
bottom; a section only starts once the decisions it depends on are made. Size is a guess: S ≤ 30
min, M ≤ 2 h, L ≥ half a day. Work that needs a live cluster is in `docs/tech-debt.md`, not here.

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
| D4 | `methodology.md` — **premise was wrong, it exists**: `report-kit@e0cd136`, `src/report_kit/templates/methodology.md`, 13 sections. All four citations resolve and are accurate (§7 "Sweep coarse to fine", §9 "Cost has exactly two terms") | vendor it to `docs/report/methodology.md` with a provenance header (source URL + commit + date) · link the citations to GitHub | **open.** Vendoring recommended: the citations must keep resolving to the text the report was written against, and an upstream edit would renumber the sections. (the `questionnaire.md` line calling it "a `methodology.md` that nobody wrote" went with that file) | 2.4, 3.4, 4.8 |
| D5 | `terraform/budgets.tf` (does not exist; no SNS or alerting exists in `terraform/` at all) | write it (~20 lines: `aws_sns_topic` + email subscription + `aws_budgets_budget`, 80% actual / 100% forecast) · delete the §5 row | **open.** "Keep the value, mark not enforced" is out: `methodology.md` §10 — a guardrail is a committable config value, and rows whose number cannot be committed are deleted, not left blank. Writing it is recommended: it is the only row in §5 not tied to one known lever, and `00-baseline` already found $175.82/month recurring plus $78.31 spent in exactly the class of drift a spend alarm catches. Threshold per D1: $640.22. **Settled: written up as `docs/tech-debt.md` #11**, given a fresh ID rather than renumbering the existing items. §5 now points there instead of at a file that does not exist | 4.7 |
| D6 | `maxReplicaCount` drift: ingestion live 10; TEI 30/30 at r1000 under a Spot quota of 256 vCPU | change config · record as is | **ingestion settled: recommend 20 ᴱ**, written into §5, §3.3 and `01-ingestion` Guardrails (which had said 50, against §5's 25 — three numbers, now one). Rationale: N=25's cap bound only at the peak, the run held a time-weighted mean of 19.5; no measurement separates 20 from 25, and the chunker's ~20 ceiling is corpus-driven. Live value raised 10 → 20 on both ScaledJobs (2026-09-19). **TEI settled: keep 30** — it carried ≥1000 req/s at steady-state p95 and ~0% error, so no Spot quota increase is requested; §5 row says so | 4.7 |
| D7 | Charts: `assets/*.svg` and `data/frontier.csv` do not exist, §3.2 and §3.6 point to them | build 2 charts from the Matrices (M) · remove the references (S) | remove for v1.0 | 2.5, 4.9 |
| D8 | `02-inference/data/*.point.md` (4 unfilled templates) | delete · keep | delete | 3.4 |
| D9 | §1 Verdict | ship · ship with guardrails · do not ship | business call, last | 4.11 |

## 0.6 · Settled 2026-09-19, applies everywhere

- **Query marginal: the broad definition.** Every row tagged to the serving pool and every NAT row counts; only what is floor by definition is subtracted (the 09-05 resting pair × 4 h + the NAT hourly fee = $0.9582). Campaign marginal $4.3706 → **$0.00375/1k queries**, against the published $0.00457. Cross-AZ transfer on serving nodes stays in: query traffic causes it. The narrow variant ($0.00331) stays in `figures.yaml` as the alternative, unused.
- **Arithmetic at full precision, rounded once at print.** This is what AWS does: 69% of this month's CUR rows carry 10 decimals, and rounding per row before summing would have overstated 2026-09 by $2.06 (1.4%).
- **Prose prints whole dollars** ($554, $457, $764). Cents stay in the §4.1 Floor table, where lines have to add up, and in rates and per-unit figures.
- **The `bedrock` control-plane endpoint is an error, not a size.** It was provisioned and billed, so it stays inside the as-built floor and is listed in the `00-baseline` errors table; figure 2 removes it. That is the one line where the two figures differ for a reason other than sizing, and it widens the gap by $26.28/month (`docs/tech-debt.md` #12).

## 0.5 · Precondition for D2 (blocks 2.1, 3.1, 3.2)

- [x] 0.5.1 CUR bucket alive (2026-09-19): `BILLING_PERIOD=2026-09` parquet, 46,905 rows, refreshed 07:22 the same morning. September is still open, so K3's month-close re-read is still owed · S
- [x] 0.5.2 Done 2026-09-19, in `figures.yaml` group `campaign_0905`. The two days rested on different hardware: 09-04 on 2 × c7i-flex.2xlarge Spot ($0.37940/h, confirmed twice, hours 17 and 18), 09-05 on c5.xlarge + c6a.xlarge ($0.18480/h + $0.00274/h EBS = **$0.18754/h**, hour 12, the only clean rest between n10 draining and r050 starting at 12:58). The 09-05 floor is 49% of the 09-04 one, which is why subtracting $0.3833/h drove r050 negative. Hour 11 is not rest: n10 was still running and TEI held 3 replicas on 3 nodes · M
- [x] 0.5.3 The published campaign figures are reconciled rather than wrong: `serving_gross` $2.4505 = instances 1.9088 + EBS 0.0365 + **cross-AZ transfer tagged to the serving nodes 0.5052**; `nat` $2.8791 = NatGateway-Bytes 2.3610 + NatGateway-Hours 0.2080 + the NAT resource's own regional bytes 0.3093 (2.8783, a $0.0008 rounding gap). CUR has not been restated: the stray ingestion run still reconciles to the cent ($0.2127). What stays wrong in `campaign.cur-actual.json` is `serving_floor_4h_usd: 0.9024` (4 h × the retired $0.2256/h) and `net_of_floor: 4.4272`; correct floor is 4 × $0.18754 = $0.7502 · S
- [ ] 0.5.3 `02-inference/data/campaign.cur-actual.json` carries `serving_floor_4h_usd: 0.9024` = 4 h × $0.2256/h — a rate retired twice (0.2256 → 0.20892 → 0.3833). `net_of_floor: 4.4272` is therefore wrong. Recompute both from 0.5.2; the §4.10 grep does not catch stale arithmetic in data files · S

## 1 · 00-baseline (finish proofreading)

- [ ] 1.1 `consolidateAfter` → 5m / 5m (live since `cfa0ab79`; 30s / 1m are plan values from `bafdc1f`). Then `01-ingestion` lines 201 and 622 stop contrasting 5m with a "frozen 30s" · S
- [ ] 1.2 TEI requests: keep `3 / 4`, add "HEAD has 6/8 since `1ef1f0a`, tech-debt #4" · S
- [ ] 1.3 Image digests: "Qdrant arm64, the rest x86_64" is wrong (chunker and indexer ran on `c7g` arm64). State what each ran on; `identity-2026-09-05.txt` records no arch · S
- [ ] 1.4 Preflight: label import is `[x]` but says "Still open" · S
- [ ] 1.5 M2 (14.3%) and R5 ($0.21163, `untaggable-2026-09-04.txt`) come from the 13:00 bootstrap hour, and the file quotes old Floor values (Karpenter $24.91/mo, "Monitoring PVs still ᴰ", open "⟨A · B⟩" LB line). Re-pull both for 18:00 from CUR, or label them "bootstrap hour". Touches Capture notes, Preflight lines 41–42, Metrics M1/M2, Retro · M
- [ ] 1.6 Cost basis still describes the old method: "every other rate is in the CUR rows", "Spot priced at what was charged in each run hour", "Reader: `aws-cur-report-export.py`" (M1 says it was not used). Rewrite: inventory from CUR, rates per unit, Spot as paid at 18:00 · S
- [ ] 1.7 `concepts.md` K3 "one measured day times a constant" → one resting hour, inventory × rate. Month-close re-read (Preflight line 52, Retro) now touches only Spot and variable lines: keep or close · S
- [ ] 1.8 `deploy/k8s/apps-applicationset.yaml`: comment says the loop is "cosmetic, no cost"; it is $74.86/month. Fix or delete the comment (AGENTS.md: no comments in config) · S
- [ ] 1.9 Final read of `index.md` · S · (`00-baseline/questionnaire.md` deleted 2026-09-19; its six problems live on as 1.1–1.8 here and as sections 2–4)

## 2 · 01-ingestion

- [~] 2.1 D23 measured 2026-09-19 for all five points, in `figures.yaml` group `d23`: each point owns one clock hour (n125→14, n75→15, n50→16, n25→17, n10→09-05 10-12), confirmed by matching CUR compute to the published per-point figures to the cent. Serving gross minus that day's rest rate gives $0.8161 / $0.5173 / $0.2935 / $0.0075 / $0.3107. NAT `Hours` is flat $0.0520 in every hour of both days, so it is floor, as assumed. **Still to write:** the Matrix `TEI $`, `$/run` and `$/1M docs` columns in `01-ingestion` and report §3.1 move with it, and the sweet spot becomes $24,875/1M docs · M
- [ ] 2.2 Lines 384–385: "two core nodes (`r7g.large`, `t3.large`)" is wrong: core is 2 × t3.large, r7g.large is the database. Check "~$0.9–1.15/hour of `baseline_other`" against the Floor (C = $1.20/h, serving $0.38/h of it) · S
- [ ] 2.3 Close: 4 open items (TEI peak at every point, CUR D23, M18 vs D30, every §3 figure marked). Do each or declare it not made · S–M
- [ ] 2.4 `methodology.md` citations: line 18, line 518, `metrics.md` D24 (per D4) · S
- [ ] 2.5 Raw data line about `frontier.csv` (per D7) · S
- [x] 2.6 Questionnaire deleted 2026-09-19. `D29` stays declared-not-made (§4.4, tech-debt #10), `methodology.md` is D4, and the "N=10 rests on one run" caveat is already in the Matrix · S

## 3 · 02-inference

- [ ] 3.1 Matrix `Serving $ (net)` and `$/1k queries` (D16) per D2. Replace the provisional paragraph under the Matrix (lines 405–421) with one line: rate, source, date · M
- [ ] 3.2 Campaign cross-check: "Marginal total" $5.33 = serving **gross** for 4 hours + NAT, so $0.00457/1k includes the serving floor (and the NAT hourly fee, if the NAT line has it). Subtract 09-05 floor node-hours for hours 12–15. Feeds report §1, §3.6, §4.2, §4.3 · M
- [ ] 3.3 r1000 ran with TEI 6/8 (`1ef1f0a`), the other points with 3/4: state it in Matrix and Saturation · S
- [ ] 3.4 `methodology.md` citation, line 18 (per D4); `data/*.point.md` and the R13 row that mentions them (per D8) · S
- [x] 3.5 Questionnaire deleted 2026-09-19. Contention is a declared scope boundary (D3), the Bedrock calibration stays open in `report.md` §1 Verdict and tech-debt #9, the `point.md` files are D8 · S

- [ ] 3.6 Pull the PrivateLink data-processing rate for `eu-central-1` from the Price List API into `price-2026-09-09.json` and `figures.yaml` → `endpoint_processed_gb` (currently `pending:`). It is the only input `D22` and report §4.5's crossover wait on; everything else in §4.5 already resolves · S
- [ ] 3.7 `ADR-0007` claims PrivateLink "slashes NAT Gateway data processing charges". §4.5 shows that is wrong by three orders of magnitude at this workload's token-to-byte ratio. Decide: amend the ADR to rest on the privacy boundary alone, or supersede it — **not** done in this pass, an ADR is a dated decision record and editing its rationale after the fact needs its own call · S

## 4 · report.md (after 1–3)

- [ ] 4.1 Header: Cost source (Floor = CUR inventory × unit rate, runs = CUR unblended); System under test says commit `1ef1f0a8` (TEI 6/8), the baseline is `cfa0ab79` (3/4); Raw data (per D7); Changes · S
- [ ] 4.2 Coverage: Idle floor row (new method); add a row for errors found at rest, excluded from the floor · S
- [ ] 4.3 §1 BLUF: floor line (per D1), retrieval cost and floor share (after 3.2). BLUF says generation is "~100x" retrieval, §4.2 says "~110x": pick one from the final numbers · S
- [ ] 4.4 §4.1: new table (A / B / C, fixed + variable, as built + right-sized); drop "⚠ provisional", "PVs still ᴰ", "2 lines still variable/unrated"; one errors line linking `00-baseline`; recount "3 of 17 Floor lines ~$0"; "Quantization … why the database line is as small as it is" contradicts the right-size (r7g.large → c7g.large); 14.3% per 1.5 · M
- [ ] 4.5 §4.2: embedding row ($3,256 − $766) per 2.1; query marginal per 3.2; floor share · S
- [ ] 4.6 §4.3: both tables and both crossovers, B per D1, marginals per 2 and 3 (script it) · S
- [ ] 4.7 §5: consolidateAfter row → 5m; budget alarm **$640.22** (right-sized B × 1.4, per D1), as built $775.37 in the second column; TEI ceiling note assumes the 6-core request (tech-debt #4 reverts to 3); the `budgets.tf` row points at tech-debt #11 (per D5); both `maxReplicaCount` rows are already rewritten (per D6) · S
- [ ] 4.8 §3.1 `TEI $`, §3.6 `$/1k queries`, §3.3 `methodology.md` line: carry from 2.1, 3.1, D4 · S
- [ ] 4.9 §3.2 and §3.6 chart references (per D7) · S / L
- [ ] 4.10 No old numbers left: `grep -rnE '426\.93|708\.72|281\.79|0\.20892|0\.2256|\$598|0\.000162|17,250|93,420|93M|provisional' docs/report` returns only intended hits · S
- [ ] 4.11 §1 Verdict (D9) · S

## 5 · Close

- [ ] 5.1 Humanizer pass on every rewritten section, plus the sentence-level Register A rewrite (one idea per sentence, at most two nesting levels) of `01-ingestion` and `02-inference`, ~600 lines each, which no pass has done yet · M
- [ ] 5.2 Confirm every gap that has no measurement is stated in the report itself: M3, Qdrant hnsw config and the EKS control-plane version → `00-baseline` Retro "Not observed" (whether the PVCs were attached is now answered by the Floor inventory, so it needs no row); M15–M17 → `01-ingestion` metrics; M11/M12 → `02-inference` Saturation; and add one line to `02-inference` §1 Unit and window: no pre-run wall-time or cost estimate survives the 2026-09-05 revision, and filling one now would pass hindsight off as foresight · S
- [ ] 5.3 `docs/tech-debt.md` numbers match the final report · S
- [ ] 5.4 Commit · S
