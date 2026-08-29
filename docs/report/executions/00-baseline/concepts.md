# 00 · Baseline — Concepts

> Mechanisms only. No instance type, threshold, count or date appears here; those are in
> `index.md`, cited by block and never copied. Kit rules are in `methodology.md` and are
> cited in one line.

| Ref | Concept | Cited from | Status |
| :--- | :--- | :--- | :--- |
| M1 | Billing granularity and the window | §1 Idle window | active |
| M2 | What counts as floor, and the A / B seam | §1 · Metrics | active |
| M3 | Attribution lag and untagged spend | §2 Journal | active |
| M4 | Vector memory is arithmetic, not a finding | Constants · Metrics | active |
| M5 | Pending instrumentation is not blocking | §1 row 1 | active |
| M6 | Qualifying an already-published idle claim | Metrics · Floor | active |

---

## M1 · Billing granularity and the window

**One line:** the cost backend reports in fixed periods, and a window that does not align to
them reports a neighbouring period's spend as this one's.

Cost data is aggregated into buckets before it is exposed. A window shorter than a bucket
returns either nothing or a whole bucket attributed to a fraction of it. A window that
straddles two buckets returns a blend. Neither failure looks like an error — both return a
plausible number. The idle window also has to span a full daily cycle, because scheduled
reconciliation, log rotation and backup jobs are floor and they are not uniformly
distributed across a day.

**Consequence:** every line of the floor table, and therefore Block B, the headline, and
the amortization bound the report derives from it.

---

## M2 · What counts as floor, and the A / B seam

**One line:** floor is what the bill shows with nobody using the system, including the
machinery that keeps it reconciled.

Controllers, the CNI, the GitOps reconciler and the monitoring stack keep running with zero
load. Turning them off to get a cleaner number measures a system that does not exist. They
are floor. The seam between A and B is a question about a hypothetical, not a measurement:
if this feature were deleted, which lines disappear from the bill? Shared cluster machinery
survives; the vector database, its volume, the embedding service and the query API do not.

The monitoring stack sits on the A side by that test, and it is worth being explicit that
it is part of the system rather than only the instrument — it would keep running for other
workloads. Dividing A by an assumed number of co-tenant features is refused because the
divisor is invented, and a headline figure built on an invented divisor is not defensible
against anyone who picks a different one.

**Consequence:** which number the report calls the cost of this feature, and whether the
break-even against Fargate compares two real options or two arbitrary ones.

---

## M3 · Attribution lag and untagged spend

**One line:** the cost backend answers about the past slowly and incompletely, and both
gaps close after the window is gone.

Attribution has to be switched on before the spend happens; it is never retroactive. Even
once on, data for a period appears hours later, and a fraction of spend arrives with no tag
at all — controller-created resources are the usual source, because the tag has to be
configured at the provisioner rather than on the resource. That fraction has to be resolved
against the total before the split is trusted, since untagged spend lands nowhere and
silently shrinks whichever block should have carried it.

**Consequence:** the A / B split, and any claim that the blocks sum to the bill.

---

## M4 · Vector memory is arithmetic, not a finding

**One line:** the memory the vector database needs follows from the embedding width, the
quantization setting and the point count — nobody chose it, and measuring it proves nothing.

It is written down because it explains a sizing decision that would otherwise look
arbitrary, and because a change to any of its three inputs changes the instance class and
therefore the dominant line of Block B. It is not a result: no run varies it, and it carries
a derived mark wherever it appears.

**Consequence:** the Qdrant instance class, and with it most of Block B.

---

## M5 · Pending instrumentation is not blocking

**One line:** a missing metric gates one claim, not the campaign, and treating it as a
campaign gate is how a measurement never happens.

The first-tier constraint reads from a series that is already collected. The second tier
reads from series that require additional scrape configuration. If that configuration lands
before the refinement points, the second tier is claimable from the points that have it. If
it never lands, one tier is reported and the second goes to the report's out-of-scope table
— which is what the rule about unproven tiers already requires (`methodology.md` §9).

**Consequence:** the schedule. A campaign that waits on a nice-to-have is a campaign that
does not run.

---

## M6 · Qualifying an already-published idle claim

**One line:** an earlier article claimed an idle cost for this architecture, and the
measured floor is the first thing that can contradict it.

The claim was made about the elastic portion of the system and read as being about the whole
of it. The measured split is what makes the distinction concrete, and the report states both
numbers rather than quietly replacing one with the other. A reader who remembers the earlier
claim and finds it unaddressed discounts the rest of the document.

**Consequence:** the credibility of the floor section, and of the article that cites it.
