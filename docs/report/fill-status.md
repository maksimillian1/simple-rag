# Report fill status — 2026-09-09

What is filled, what is still open, and which decisions only the project owner can make. Every
filled number cites its source inline in the file where it landed; this file is an index and
does not repeat that content.

---

## What was filled

- **`report.md`** — 123 → 0 placeholders. BLUF, Coverage, both run-matrix tables (rebuilt to
  match the grid actually swept rather than the abandoned original plan), the §4 cost tables,
  §5 Guardrails.
- **`00-baseline/index.md`** — 31 → 2, both intentional enumeration notation rather than blanks.
  Includes the compute-rate fix (partial-hour billing bug, core and database corrected) and the
  split between bootstrap traffic and idle traffic.
- **`01-ingestion/index.md`** — 17 → 1 (bash example syntax). `01-ingestion/metrics.md` — 27 → 3
  (M15–M17, never implemented).
- **`02-inference/index.md`** — 39 → 1 open (the pre-run wall-time and cost estimate, listed
  below), plus bash example syntax left as-is.
- Two stale ledger patterns were fixed the same way in both executions. Unrun grid points
  (`n04`, `n24`, `r005`) now say they were not run instead of sitting as empty rows, and the stale
  "decision after the coarse pass" placeholder in each now records what happened.

## What can't be filled

These needed a live system, and the cluster is gone:

- `00-baseline`: M3 (node inventory), confirmation of the Qdrant hnsw config, the EKS
  control-plane version (Terraform's default is used, never read live), and whether the Qdrant
  and Monitoring PVCs were attached
- `01-ingestion`: `M15`–`M17` (TEI queue depth, TEI inference duration, Qdrant latency). They are
  blocked further upstream: TEI's own `/metrics` returns HTTP 200 with an empty body
- `02-inference`: the same `M11`/`M12` gap, and the contention pass (§3.8), which never ran and is
  the largest open item in the report
- The `apps-serving` and Karpenter Fargate compute rates stay `⚠ provisional`. They carry the same
  partial-hour billing bug that was found and fixed for `core-on-demand` and
  `database-on-demand`, but this pool's nodes were churning through consolidation (4 different
  Spot instance types in one hour), so there is no single clean rate to recover the way there was
  for the other two
- `02-inference` §1: "5 points × wall time · $, spaced by convergence" was a pre-run estimate.
  Nothing records what it said before the 2026-09-05 revision. Filling it now with hindsight
  numbers would pass them off as foresight, so it stays a gap

## Two dangling references, found and not fixed

- `methodology.md` is cited by name in `01-ingestion` (§1 Sweep order, `D24`'s formula note) and
  `02-inference` (§1 Sweep order). The file does not exist in this repo.
- `terraform/budgets.tf` is cited in `report.md`'s Guardrails table as the place that enforces the
  budget alarm. It doesn't exist either, and no budget alarm is live.

Both are noted inline where cited. Whether to write the missing files or remove the references is
a decision, listed below.

---

## Questionnaires: decisions only you can make

Each questionnaire sits next to the file its questions are about:

- **`questionnaire.md`** (next to `report.md`) — the ship/no-ship verdict, two places where live
  config disagrees with a finding (`maxReplicaCount` settings), the missing `terraform/budgets.tf`
- **`executions/00-baseline/questionnaire.md`** — the duplicate-PVC pattern (Qdrant and
  Monitoring), and whether the `⚠ provisional` `apps-serving` rate is worth a clean re-capture
- **`executions/01-ingestion/questionnaire.md`** — whether `D29`/Fargate is worth finishing, the
  `methodology.md` reference gap, a one-run caveat on N=10
- **`executions/02-inference/questionnaire.md`** — the contention pass (the largest open item in
  the report), whether `E18`/generation is worth a real calibration run, the same
  `methodology.md` gap, the stale `data/*.point.md` files

---

## AGENTS.md pass

Applied `.agents/AGENTS.md`'s Communication Principles and Register A/B rules:

- `00-baseline/index.md` was cut from 348 to 213 lines. A duplicated paragraph was removed, and
  the multi-generation "found X, then found Y which reverses X" narrative was replaced with flat
  current-state statements.
- Across all 4 files, the 5 remaining "see above"/"see below" references were fixed (`report.md`
  ×2, `02-inference` ×2, `01-ingestion` ×1). The style guide forbids them.
- `01-ingestion` and `02-inference` were read end to end. Nothing turned up that was worth cutting
  for low value. The tangents that look like dev-ops notes (a gitops-engine panic, script bugs
  found mid-campaign) decide whether specific data points can be trusted, which is what this
  document type is for. One was checked against `tmp/post-mortem/` first, to confirm it wasn't
  only a duplicate, before it was kept. The read did find a stale Close-checklist checkbox in
  both docs: "Outcome compared against Expected in Retro" was unchecked although the Retro section
  below it satisfies it. Fixed in both. `01-ingestion` also had "Saturation identified" unchecked
  although §3 Saturation states the finding, and "Collection point count written back into
  `00-baseline`" unchecked and never done. Both are done now (84,018, `00-baseline` §2 Envelope).
  `02-inference` had the same "Saturation identified" gap, fixed the same way. One factual bug
  turned up as well: `01-ingestion`'s Retro said "Month-close revision — not yet checked... CUR
  pull is ~24h old," which contradicted its own Close checklist four lines above, where the 48h
  re-check is recorded as done on 2026-09-07. The sentence predated the re-check and was never
  updated. Fixed.
- Not done: a sentence-level Register A rewrite (one idea per sentence, at most two nesting
  levels) of either file's ~600 lines. The end-to-end read checked correctness and value, not
  prose density. Much of the density comes from analytical chains that ran over several days (the
  ramp-versus-steady-state corrections, the NAT-methodology bug). Compressing them without losing
  the "what happened → why → what it means" order the style guide asks for takes editorial
  judgment rather than a mechanical pass.
