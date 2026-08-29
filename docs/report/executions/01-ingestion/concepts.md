# 01 · Ingestion concurrency — Concepts

Mechanisms only. Values are in `index.md` and `metrics.md`, cited by block. Refs are cited from
outside as `01-ingestion/K1`.

## K1 · The run window closes at zero nodes, not at queue drain

**One line** — nodes keep billing after the last document, and that tail is the mechanism the
report exists to demonstrate.

A node is billed from the moment it is provisioned. It produces work only after it boots, pulls
the container image and initialises the runtime. It is billed again for a tail after the last
document, until consolidation removes it. Both windows produce zero units at full price.

Closing the window when the queues empty excludes that tail from every cost figure. The unit
cost then falls monotonically with concurrency, because the thing that makes it turn back up has
been measured out of existence. The chart keeps its shape and loses its mechanism.

**Consequence** — every `$/run`, and whether the U-curve exists in the report at all.

## K2 · Packing density is a condition, not a result

**One line** — how many workers fit on one node decides how much warm-up each document pays for,
and it is fixed by two frozen values rather than measured.

Pod requests and the pinned instance type together set workers per node. Denser packing spreads
one node's warm-up across more documents and moves the unit-cost minimum to the right. Sparser
packing moves it left.

No run varies it. Every figure on the frontier is conditional on the ratio, so the ratio belongs
in the report envelope rather than among its findings. A later change to pod requests invalidates
the concurrency guardrail without changing anything the guardrail names.

**Consequence** — where the sweet spot sits, and whether the guardrail derived from it survives a
change to pod requests.
