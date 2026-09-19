# simple-rag

## Project rules

The engineering and architecture rules for this repository live in
[.agents/AGENTS.md](.agents/AGENTS.md) — directory boundaries, the Haystack and
Go API constraints, the IaC and GitOps conventions, and the tagging policy.
Read it before writing code or infrastructure.

`docs/architecture.md` is the single source of truth for lifecycle, data
routing and component boundaries; `.agents/AGENTS.md` defers to it.

## The report

`docs/report/` is an engineering report with a number contract, and it is the
one place in this repository where prose is load-bearing.

- `figures.yaml` is the registry: every number the report prints resolves from
  it. Nothing is computed in prose.
- `formats.md` is the contract for how a number is written and marked.
- `methodology.md` is why the structure is shaped this way. Both are vendored
  from report-kit and carry a provenance header — edit upstream, not here.
- `report-kit figures check` verifies that every marked number still equals what
  the registry resolves. Run it from `docs/report/` before calling a change to
  the report done. The command ships with report-kit, pinned to a tag in
  `docs/report/requirements.txt` — install it with
  `pip install -r docs/report/requirements.txt`.

A hook in `.claude/settings.json` states the contract before an edit under
`docs/report/` and runs the checker after one. It informs rather than blocks,
so a failing check is a message, not a wall — see `.claude/hooks/report-guard.py`.
