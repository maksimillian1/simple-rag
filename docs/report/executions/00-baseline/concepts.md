# Baseline — Concepts

Mechanisms only. No instance type, threshold, count or date appears here; those are in
`index.md`, cited by block. Cited from elsewhere by path: `00-baseline/K1`.

| Ref | Concept | Cited from |
| :--- | :--- | :--- |
| K1 | Billing granularity and the window | `index.md` §1 Preflight · `metrics.md` M1 |
| K2 | What counts as floor, and the A / B seam | `index.md` §2 Floor |
| K3 | Attribution lag and untagged spend | `index.md` §1 Preflight · `metrics.md` M2 |
| K4 | Vector memory is arithmetic, not a finding | `index.md` §2 Configuration freeze · Floor |
| K5 | Pending instrumentation is not blocking | `01-ingestion` §1 Metrics |
| K6 | Qualifying an already-published idle claim | `index.md` §2 Floor · report §4.1 |
| K7 | Why the run window closes at zero nodes, not at queue drain | `01-ingestion` §1 Window |
| K8 | Packing density is a condition, not a result | `01-ingestion` §1 Axis · report §2 |

---

## K1 · Billing granularity and the window

**One line** — the cost backend reports in fixed periods, and a window that does not align to
them reports a neighbouring period's spend as this one's.

Cost data is aggregated into buckets before it is exposed. A window shorter than a bucket
returns either nothing or a whole bucket attributed to a fraction of it; a window straddling
two returns a blend. Neither failure looks like an error — both return a plausible number.
The idle window also has to span a full daily cycle, because scheduled reconciliation, log
rotation and backup jobs are floor and are not uniformly distributed across a day.

**Consequence** — every floor line, and therefore Block B, the headline, and the amortization
bound derived from it.

**Refs** — M1

---

## K2 · What counts as floor, and the A / B seam

**One line** — floor is what the bill shows with nobody using the system, including the
machinery that keeps it reconciled.

Controllers, the CNI, the GitOps reconciler and the monitoring stack keep running at zero
load. Turning them off to get a cleaner number measures a system that does not exist. They
are floor. The seam between A and B is a question about a hypothetical rather than a
measurement: if this feature were deleted, which lines leave the bill? Shared cluster
machinery survives; the vector database, its volume, the embedding service and the query API
do not. The monitoring stack sits on the A side by that test — it is part of the system and
not only the instrument, and it would keep running for other workloads.

**Consequence** — which number the report calls the cost of this feature, and whether the
break-even against Fargate compares two real options or two arbitrary ones.

**Refs** — M1 · D5 · E7

---

## K3 · Attribution lag and untagged spend

**One line** — the cost backend answers about the past slowly and incompletely, and both gaps
close only after the window is gone.

Attribution has to be switched on before the spend happens; it is never retroactive. Even
once on, data for a period appears hours later, and a fraction of spend arrives with no tag
at all. Controller-created resources are the usual source, because the tag has to be
configured at the provisioner rather than on the resource. That fraction is resolved against
the total before the split is trusted: untagged spend lands nowhere and silently shrinks
whichever block should have carried it.

**Consequence** — the A / B split, and any claim that the blocks sum to the bill.

**Refs** — M1 · M2

---

## K4 · Vector memory is arithmetic, not a finding

**One line** — the memory the vector database needs follows from embedding width, the
quantization setting and the point count; nobody chose it, and measuring it proves nothing.

It is written down because it explains a sizing decision that would otherwise look arbitrary,
and because a change to any of its three inputs changes the instance class and therefore the
dominant line of Block B. No run varies it, and it carries a derived mark wherever it appears.

**Consequence** — the Qdrant instance class, and with it most of Block B.

**Refs** — D6 · R4

---

## K5 · Pending instrumentation is not blocking

**One line** — a missing metric gates one claim, not the campaign, and treating it as a
campaign gate is how a measurement never happens.

The first constraint tier reads from a series that is already collected. The second reads
from series that need additional scrape configuration. If that configuration lands before the
refinement points, the second tier is claimable from the points that have it. If it never
lands, one tier is reported and the second becomes a Coverage row — which is what the rule
about unproven tiers already requires (`methodology.md` §8).

**Consequence** — the schedule. A campaign that waits on a nice-to-have is a campaign that
does not run.

**Refs** — `01-ingestion/M8` · `M9` · `M10`

---

## K6 · Qualifying an already-published idle claim

**One line** — an earlier article claimed an idle cost for this architecture, and the measured
floor is the first thing that can contradict it.

The claim was made about the elastic portion of the system and reads as being about the whole
of it. The measured split is what makes the distinction concrete, and the report states both
numbers rather than quietly replacing one with the other. A reader who remembers the earlier
claim and finds it unaddressed discounts the rest of the document.

**Consequence** — the credibility of the floor section, and of the article that cites it.

**Refs** — E7

---

## K7 · Why the run window closes at zero nodes, not at queue drain

**One line** — nodes keep billing after the last document, and that tail is the mechanism the
report exists to demonstrate.

A node is billed from provisioning, but produces work only after boot, image pull and runtime
init; it is billed again for a tail after the last document until consolidation removes it.
Both windows produce zero units at full price. Closing the window when the queues empty
excludes the tail from every cost figure, which deletes the effect that turns the unit-cost
curve back up at high concurrency — and leaves a chart with a shape and no mechanism.

**Consequence** — every `$/run`, and the existence of the U-curve in report §3.4.

**Refs** — `01-ingestion/M2` · `M3` · `M4` · `D19`

---

## K8 · Packing density is a condition, not a result

**One line** — how many workers fit on one node decides how much warm-up each document pays
for, and it is fixed by two frozen values rather than measured.

Pod requests and the pinned instance type together set workers per node. Denser packing
amortises per-node warm-up across more work and moves the unit-cost minimum to the right;
sparser packing moves it left. No run varies it, so every figure on the frontier is
conditional on the ratio, and the ratio belongs in the report envelope rather than in its
findings.

**Consequence** — where the sweet spot sits, and whether the guardrail derived from it
survives a change to pod requests.

**Refs** — `index.md` §2 Configuration freeze
