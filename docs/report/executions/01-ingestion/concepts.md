# 01 · Ingestion concurrency — Concepts

Mechanisms only. Values are in `index.md` and `metrics.md`. Cited from outside as
`01-ingestion/K1`.

## K1 · A node bills before its first pod and after its last

Boot, image pull and the consolidation tail are billed and produce zero units. Closing the window
at queue drain excludes them, and the unit cost then falls monotonically because the thing that
turns it back up was measured out of existence. The Kubernetes node series starts at kubelet
registration and ends at object deletion, so it misses both edges — the bill does not.

**Consequence** — every `$/run`, and whether the U-curve exists in the report at all.

## K2 · Packing density is a condition, not a result

Pod requests and the pinned instance type set workers per node, and no run varies either. Denser
packing spreads one node's warm-up across more documents and moves the unit-cost minimum right.

**Consequence** — where the sweet spot sits, and why a later change to pod requests invalidates
the concurrency guardrail without touching anything the guardrail names.

## K3 · The sampled peak is a floor; the OOM count is the ceiling

A SPLADE forward pass allocates and releases inside one call, shorter than any scrape interval,
so the sampled maximum is always low. The kernel misses nothing: zero terminations at a limit
proves that limit held, and a non-zero count proves it did not.

*A crossed limit is raised, never refitted to a peak already known to be too low.*

**Consequence** — whether the two memory guardrails are ceilings or wishes.

## K4 · The sizing arithmetic and the memory reading are not the same quantity

The formula prices one INT8 copy of the dense vectors and omits the HNSW graph and the sparse
index; the container reading includes page cache on memory-mapped segments. One is biased down,
the other up.

*The reading rises with query traffic and falls after a restart while the collection is
unchanged.*

**Consequence** — that the check is a magnitude test, never an equality.

## K5 · TEI is shared and elastic, so part of a serving bill is an ingestion cost

The indexer drives the same autoscaled deployment the API drives, so a run raises the serving
pool bill with no worker node on that pool. Subtracting the pool's idle rate removes the
always-on floor; the split between pods inside a node is an AWS allocation rule over requests
with a fixed CPU-to-memory weighting, not a measurement.

*Unused cost is the exception — capacity billed with no pod on it needs no convention.*

**Consequence** — whether a run is priced completely, and why a point must open with the shared
tier at its minimum.

## K6 · The bill is hourly and it arrives late

Line items carry sub-hour amounts but aggregate into clock hours, so two runs in one hour arrive
as one summed row that cannot be separated afterwards. Delivery is daily and figures are revised
until the month closes, so cost cannot be read when a run ends.

**Consequence** — one point per hour, and a cost pass days after the campaign rather than a
column filled at close.

## K7 · N is a ceiling, and only a full queue makes it behave like a setting

`maxReplicaCount` grants permission to run N workers; KEDA fills it only while messages wait.
The corpus is dropped in full before the window opens, so a raised ceiling is consumed
immediately. What each point actually ran at is M5, and it diverges from N when Spot capacity
is short. On a client-driven path the same axis moves nothing, which is why `02-inference`
sweeps arrival rate instead.

**Consequence** — that the frontier's x-axis is M5 rather than N, and that this axis does not
transfer to the query path.
