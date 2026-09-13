# 00-baseline — open decisions

## Decisions

None open. Resolved: Floor re-based on the resting hour; orphaned volumes deleted by the owner on
2026-09-11 ($75.35 spent) and teardown rewritten (untested, `docs/tech-debt.md` #3); EKS
control-plane logs recorded as an error and switched off in Terraform; ArgoCD upgrade and the
On-Demand serving base moved to `docs/tech-debt.md` #1 and #6; right-sized figure 2 written with
On-Demand serving.

## Problems (facts, no decision needed)

| # | Where | Says | Actually |
| :--- | :--- | :--- | :--- |
| 1 | index.md, Configuration freeze, `consolidateAfter` | apps-compute 30 s, apps-serving 1 m | 5m on both since `cfa0ab79` (live at capture); 30s/1m are plan values from `bafdc1f`. Same error in `report.md` §5 |
| 2 | index.md, Configuration freeze, TEI requests | `cpu 3 / 4` | true at capture; HEAD has `6000m / 8000m` from `1ef1f0a`, so a cluster launched from HEAD is not the baselined system (`docs/tech-debt.md` #4) |
| 3 | index.md, Configuration freeze, image digests | Qdrant `arm64`, the rest `x86_64` | chunker and indexer run only on `c7g` (arm64); `identity-2026-09-05.txt` records no architecture |
| 4 | index.md, Preflight | `[x]` label import, text says "Still open" | checkbox contradicts its text |
| 5 | `report.md`, `01-ingestion`, `02-inference` | Block B $426.93, C $708.72, serving idle rate $0.20892/h | Floor is now C $877.54 (fixed $866.79 + variable $10.75), right-sized $790.30; serving $0.3833/h. Net-of-floor in 01/02 and report §1, §4.1, §4.3, §5 need the new numbers (r050 net goes negative) |
| 6 | `deploy/k8s/apps-applicationset.yaml` comment | Qdrant loop is "cosmetic, no cost" | $74.86/month at rest (`docs/tech-debt.md` #1) |
