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

The same argument decides where node-hours come from. A Kubernetes-sourced node series opens at
kubelet registration and closes at node object deletion, and both edges sit inside the billed
interval. The slivers it excludes are boot and teardown, which are the two intervals this
concept is about. The bill does not exclude them, so the bill is the source and the Kubernetes
series is the shape.

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

## K3 · A sampled peak is a lower bound, and the OOM count is what bounds it

**One line** — the allocation the memory guardrail is meant to survive is shorter than the
interval that samples it, so the sampled figure is a floor and not a ceiling.

A SPLADE forward pass allocates a tensor sized by batch and sequence length, and releases it
inside the same call. A sampler reading every few seconds returns whatever the process happened
to hold at the sample instant, never the maximum it reached. Shortening the export interval
narrows the gap and cannot close it.

The termination counter is the other half of the pair, and it carries authority the sampler does
not. A limit under which no container was killed is a proven ceiling whether or not the sampler
caught the spike, because the kernel observed every allocation. A non-zero count says the
opposite with the same authority: the limit was crossed, and a replacement fitted to the sampled
peak would be fitted to a number already known to be too low. A crossed limit is raised, not
refitted.

**Consequence** — whether the two memory guardrails are ceilings or wishes, and what a run with
zero terminations is entitled to claim.

## K4 · Quantization and page cache make the sizing check a magnitude test

**One line** — the arithmetic prices one copy of the dense vectors and the measurement reads
everything the container has touched, so the two agree only by coincidence.

Under scalar quantization Qdrant holds a one-byte-per-dimension copy resident and leaves the
float32 originals on disk. Reading bytes per dimension as four overstates the resident set
fourfold. The arithmetic also prices dense vectors alone: the HNSW graph is a separate term that
grows with the configured link count, and the sparse index built from SPLADE output is not in
the formula at all. Two of those omissions push the estimate down and one pushes it up.

The measurement carries the opposite bias. Working set for the Qdrant container includes page
cache charged to its cgroup, and collection segments are memory-mapped. The reading therefore
describes how much of the collection has been touched since the process started, not how much
must stay resident. It rises with query traffic and falls after a restart while the collection is
unchanged.

**Consequence** — whether the sizing check can be stated as an equality, and what the instance
class behind the Qdrant floor line was actually sized against.

## K5 · TEI is shared, elastic, and split by an allocation rule

**One line** — the embedding tier is not frozen and not owned by either path, so part of a
serving bill belongs to an ingestion run, and the boundary that assigns it is drawn by AWS.

The indexer calls the same TEI deployment the query API calls, and that deployment autoscales
from two replicas. A concurrent ingestion run therefore raises the serving pool bill without any
worker node existing on that pool. Reading only the ingestion pool would understate the run;
reading the whole serving pool would fold two always-on replicas into a marginal figure. What
belongs to the run is the difference between the two, which is why the idle rate of the pool is
captured at baseline and subtracted from every window.

The subtraction is a floor removal, not an allocation. The allocation problem sits one level
down, inside a node that holds several pods. Only the instance is billed; the division of that
one charge across the pods on it is performed by AWS using their CPU and memory against a fixed
weighting. The total is exact — it is the line item. The internal boundary is a convention, and
a different convention would move it without any pod behaving differently.

Two properties of the convention matter. The CPU-to-memory weighting is fixed by AWS and does
not follow the instance type actually running, so a memory-heavy pod on a CPU-heavy node is
charged against a ratio the hardware does not have. And allocation reads pod requests, so a pod
that declares none can be dropped from the split rather than estimated — which would make a
worker vanish from a decomposition whose total still matches the bill.

The unused figure is the useful half and carries none of that ambiguity. Capacity billed with no
pod on it is warm-up before the first pod starts, the tail after the last one exits, and the
slack left by pods that do not tile the node evenly. That is one number for the whole mechanism
behind the U-curve, measured rather than reconstructed from two timestamps.

**Consequence** — whether an ingestion run is priced completely, how far the per-component row
in the marginal table can be pushed, and why a run must open with the shared tier at its minimum.

## K6 · The bill is hourly and it arrives late

**One line** — cost is aggregated into clock hours and delivered a day or more afterwards, which
decides how points are scheduled and when a cost figure may be written down.

Line items carry sub-hour usage amounts but are aggregated into hourly buckets. A twenty-minute
run inside one hour is visible and correctly priced. Two runs inside the same hour are not: they
arrive as one row per resource with one summed amount, and nothing in the export says which
minutes belonged to which. The ingestion pool sits at zero between points, so a bucket that
contains one window contains one point and nothing else — provided no second point is started
before the hour rolls over.

Delivery is the second half. The export is written at least daily and revised as the month
progresses, so a figure read the same day is provisional and a figure read before the export
lands does not exist. Nothing about a run recovers this by waiting differently: the window and
the saturation signal are perishable and belong to the moment the run ends, while the cost
belongs to a pass run days later. Treating them as one step means either the run ledger waits
for the bill, or the bill is guessed.

**Consequence** — the minimum spacing between points, which columns of the run ledger are filled
when, and whether a cost figure in the report is final or still moving.
