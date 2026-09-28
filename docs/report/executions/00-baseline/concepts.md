# 00 · Baseline — Concepts

Mechanisms only. Values are in `index.md`. Cited from outside as `00-baseline/K1`.

## K1 · Every provisioner tags separately, and applying is not activating

Terraform's `default_tags` cover only what Terraform creates: Karpenter tags from its node class,
a managed node group only through a launch template, the CSI driver from storage class parameters
that are immutable after creation. A key also becomes a billing column only after activation in
the payer account. A key applied everywhere and activated nowhere reads as untagged, and nothing
fails.

**Consequence** — whether any Floor block means what it says, and whether an untagged reading is
a real gap or a missing click.

## K2 · The export answers nothing about the time before it existed

The detailed export holds no data from before its creation, and pod-level splitting prices
containers only while they are alive. A pod that declared no resource requests can also vanish
from the split while the total still reconciles against the bill.

*Example: correct cluster, export created after the campaign: full Prometheus data, zero cost
data, re-run everything.*

**Consequence** — the earliest moment any window may open, and which preparation a re-run cannot
repair.

## K3 · The monthly floor is one resting hour projected

The floor is not a bill for a month, or for a day. CUR gives the inventory of one resting hour
and what it was billed for; the month is that inventory times a published unit rate times 730
(`docs/report/methodology.md` §9). The multiplier is a rate convention and is exact. What is assumed is that
the hour is typical, and one hour catches neither a daily nor a weekly cycle.

Spot is where the assumption bites hardest: a spot line carries that hour's price into all 730,
and the two resting hours this report captured differ by half. The month-close re-read therefore
touches only the lines that can still move — Spot and the variable ones; the inventory and the
published rates will not change once the period is closed.

**Consequence** — how much of the headline floor is measurement and how much is arithmetic, which
hour each projected line rests on, and why the floor is read twice.
