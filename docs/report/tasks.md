# Report tasks

Numbers flow one way: `00-baseline` → `01-ingestion` / `02-inference` → `report.md`. Work top to
bottom; a section only starts once the decisions it depends on are made. Size is a guess: S ≤ 30
min, M ≤ 2 h, L ≥ half a day. Work that needs a live cluster is in `docs/tech-debt.md`, not here.

## Settled numbers (from `00-baseline` Floor)

| Figure | As built | Right-sized ᴱ |
| :--- | ---: | ---: |
| Block A (fixed + variable) | 323.70 (313.88 + 9.82) | 306.71 (296.89 + 9.82) |
| Block B (fixed + variable) | 553.84 (552.91 + 0.93) | 483.59 (482.66 + 0.93) |
| Block C | 877.54 | 790.30 |
| Serving pool idle rate, 09-04 18:00 | $0.3833/h | — |
| Errors, recurring at rest (ArgoCD 65.81 + 9.05, EKS logs 100.96) | 175.82/month | — |
| Errors, already spent (PVCs 75.35, logs 2.26, standalone EBS 0.70) | 78.31 | — |
| Cluster startup | 0.61 per launch | — |

Valid only while the §4.2 marginals stay as they are ($0.02475/doc, $0.00457/1k queries); redo
after sections 2 and 3:

| Derived | B as built | B right-sized |
| :--- | ---: | ---: |
| Docs/month where floor share = 50% | 22,377 | 19,539 |
| Queries/month where floor share = 50% | 121.2M | 105.8M |
| Floor share per 1k queries at 1000 req/s | $0.000211 | $0.000184 |
| Budget alarm, B × 1.4 | $775.38 | $677.03 |

## 0 · Decisions (they block the numbers)

| # | Decision | Options | Recommendation | Blocks |
| :--- | :--- | :--- | :--- | :--- |
| D1 | Which Block B is the headline | as built $553.84 · right-sized $483.59 · both | both in §1 and §4.1; §4.3 and §5 on as built (measured inventory) | 4.3–4.7 |
| D2 | How run costs net out the serving floor | (a) 09-04 rate $0.3833/h for every run: r050 net goes negative · (b) each run day's own resting serving inventory from CUR (09-05 serving ran on xlarge nodes, not 2xlarge) · (c) keep per-point figures gross for relative comparison, net only at campaign level | (b) + (c) | 2.1, 3.1, 3.2 |
| D3 | Re-run a cluster for the contention pass, real Bedrock, `D29`, `M15`–`M17`? | re-run · ship v1.0 with the gaps declared | ship; they are tech-debt #7–#9 | 2.6, 3.5, 5.2 |
| D4 | `methodology.md` (cited 4 times, does not exist) | write it · remove the citations, inline one line per rule | remove + inline | 2.4, 3.4, 4.8 |
| D5 | `terraform/budgets.tf` (does not exist) | write it · keep the value in §5, mark "not enforced" | keep the value, mark not enforced | 4.7 |
| D6 | `maxReplicaCount` drift: ingestion live 10 vs sweet spot 25; TEI 30/30 at r1000 under a Spot quota of 256 vCPU | change config (→ tech-debt) · record as is | record as is in §5 | 4.7 |
| D7 | Charts: `assets/*.svg` and `data/frontier.csv` do not exist, §3.2 and §3.6 point to them | build 2 charts from the Matrices (M) · remove the references (S) | remove for v1.0 | 2.5, 4.9 |
| D8 | `02-inference/data/*.point.md` (4 unfilled templates) | delete · keep | delete | 3.4 |
| D9 | §1 Verdict | ship · ship with guardrails · do not ship | business call, last | 4.11 |

## 1 · 00-baseline (finish proofreading)

- [ ] 1.1 `consolidateAfter` → 5m / 5m (live since `cfa0ab79`; 30s / 1m are plan values from `bafdc1f`). Then `01-ingestion` lines 201 and 622 stop contrasting 5m with a "frozen 30s" · S
- [ ] 1.2 TEI requests: keep `3 / 4`, add "HEAD has 6/8 since `1ef1f0a`, tech-debt #4" · S
- [ ] 1.3 Image digests: "Qdrant arm64, the rest x86_64" is wrong (chunker and indexer ran on `c7g` arm64). State what each ran on; `identity-2026-09-05.txt` records no arch · S
- [ ] 1.4 Preflight: label import is `[x]` but says "Still open" · S
- [ ] 1.5 M2 (14.3%) and R5 ($0.21163, `untaggable-2026-09-04.txt`) come from the 13:00 bootstrap hour, and the file quotes old Floor values (Karpenter $24.91/mo, "Monitoring PVs still ᴰ", open "⟨A · B⟩" LB line). Re-pull both for 18:00 from CUR, or label them "bootstrap hour". Touches Capture notes, Preflight lines 41–42, Metrics M1/M2, Retro · M
- [ ] 1.6 Cost basis still describes the old method: "every other rate is in the CUR rows", "Spot priced at what was charged in each run hour", "Reader: `aws-cur-report-export.py`" (M1 says it was not used). Rewrite: inventory from CUR, rates per unit, Spot as paid at 18:00 · S
- [ ] 1.7 `concepts.md` K3 "one measured day times a constant" → one resting hour, inventory × rate. Month-close re-read (Preflight line 52, Retro) now touches only Spot and variable lines: keep or close · S
- [ ] 1.8 `deploy/k8s/apps-applicationset.yaml`: comment says the loop is "cosmetic, no cost"; it is $74.86/month. Fix or delete the comment (AGENTS.md: no comments in config) · S
- [ ] 1.9 Final read of `index.md`; delete `00-baseline/questionnaire.md` · S

## 2 · 01-ingestion

- [ ] 2.1 `TEI $` (D23, N=25–125) is still the pre-CUR estimate ᴰ. Recompute per D2, close the two D23 items in Close. NAT `Hours` inside `Other $` is floor too ($0.052/h, ~2% of NAT). Feeds report §3.1 and §4.2 ($766 floor share) · M
- [ ] 2.2 Lines 384–385: "two core nodes (`r7g.large`, `t3.large`)" is wrong: core is 2 × t3.large, r7g.large is the database. Check "~$0.9–1.15/hour of `baseline_other`" against the Floor (C = $1.20/h, serving $0.38/h of it) · S
- [ ] 2.3 Close: 4 open items (TEI peak at every point, CUR D23, M18 vs D30, every §3 figure marked). Do each or declare it not made · S–M
- [ ] 2.4 `methodology.md` citations: line 18, line 518, `metrics.md` D24 (per D4) · S
- [ ] 2.5 Raw data line about `frontier.csv` (per D7) · S
- [ ] 2.6 Resolve the questionnaire (per D3, D4), then delete it · S

## 3 · 02-inference

- [ ] 3.1 Matrix `Serving $ (net)` and `$/1k queries` (D16) per D2. Replace the provisional paragraph under the Matrix (lines 405–421) with one line: rate, source, date · M
- [ ] 3.2 Campaign cross-check: "Marginal total" $5.33 = serving **gross** for 4 hours + NAT, so $0.00457/1k includes the serving floor (and the NAT hourly fee, if the NAT line has it). Subtract 09-05 floor node-hours for hours 12–15. Feeds report §1, §3.6, §4.2, §4.3 · M
- [ ] 3.3 r1000 ran with TEI 6/8 (`1ef1f0a`), the other points with 3/4: state it in Matrix and Saturation · S
- [ ] 3.4 `methodology.md` citation, line 18 (per D4); `data/*.point.md` and the R13 row that mentions them (per D8) · S
- [ ] 3.5 Resolve the questionnaire (per D3), then delete it · S

## 4 · report.md (after 1–3)

- [ ] 4.1 Header: Cost source (Floor = CUR inventory × unit rate, runs = CUR unblended); System under test says commit `1ef1f0a8` (TEI 6/8), the baseline is `cfa0ab79` (3/4); Raw data (per D7); Changes · S
- [ ] 4.2 Coverage: Idle floor row (new method); add a row for errors found at rest, excluded from the floor · S
- [ ] 4.3 §1 BLUF: floor line (per D1), retrieval cost and floor share (after 3.2). BLUF says generation is "~100x" retrieval, §4.2 says "~110x": pick one from the final numbers · S
- [ ] 4.4 §4.1: new table (A / B / C, fixed + variable, as built + right-sized); drop "⚠ provisional", "PVs still ᴰ", "2 lines still variable/unrated"; one errors line linking `00-baseline`; recount "3 of 17 Floor lines ~$0"; "Quantization … why the database line is as small as it is" contradicts the right-size (r7g.large → c7g.large); 14.3% per 1.5 · M
- [ ] 4.5 §4.2: embedding row ($3,256 − $766) per 2.1; query marginal per 3.2; floor share · S
- [ ] 4.6 §4.3: both tables and both crossovers, B per D1, marginals per 2 and 3 (script it) · S
- [ ] 4.7 §5: consolidateAfter row → 5m; budget alarm B × 1.4; TEI ceiling note assumes the 6-core request (tech-debt #4 reverts to 3); `budgets.tf` per D5; `maxReplicaCount` per D6 · S
- [ ] 4.8 §3.1 `TEI $`, §3.6 `$/1k queries`, §3.3 `methodology.md` line: carry from 2.1, 3.1, D4 · S
- [ ] 4.9 §3.2 and §3.6 chart references (per D7) · S / L
- [ ] 4.10 No old numbers left: `grep -rnE '426\.93|708\.72|281\.79|0\.20892|0\.2256|\$598|0\.000162|17,250|93,420|93M|provisional' docs/report` returns only intended hits · S
- [ ] 4.11 §1 Verdict (D9) · S

## 5 · Close

- [ ] 5.1 Humanizer pass on every rewritten section · M
- [ ] 5.2 Delete `fill-status.md` (2026-09-09 snapshot, superseded by this file) and `questionnaire.md` once D3–D9 are written into the report · S
- [ ] 5.3 `docs/tech-debt.md` numbers match the final report · S
- [ ] 5.4 Commit · S
