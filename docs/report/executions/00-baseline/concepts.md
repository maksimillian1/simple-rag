# 00 · Baseline — Concepts

Mechanisms only. Values are in `index.md`. Cited from outside as `00-baseline/K1`.

## K1 · Every provisioner tags separately, and applying is not activating

Terraform's `default_tags` cover only what Terraform creates: Karpenter tags from its node class,
a managed node group only through a launch template, the CSI driver from storage class parameters
that are immutable after creation. A key also becomes a billing column only after activation in
the payer account — applied everywhere and activated nowhere reads as untagged with nothing
failing.

**Consequence** — whether any Floor block means what it says, and whether an untagged reading is
a real gap or a missing click.

## K2 · The export answers nothing about the time before it existed

The detailed export holds no data from before its creation, and pod-level splitting prices
containers only while they are alive. A pod that declared no resource requests can also vanish
from the split while the total still reconciles against the bill.

*Example: correct cluster, export created after the campaign — full Prometheus data, zero cost
data, re-run everything.*

**Consequence** — the earliest moment any window may open, and which preparation a re-run cannot
repair.

## K3 · The monthly floor is one measured day times a constant

The 730-hour multiplier is a rate convention and is exact; the assumption that the captured day
is typical is not. A daily cycle catches daily jobs and nothing weekly, and line items keep
moving until the billing period closes.

**Consequence** — how much of the headline floor is measurement and how much is arithmetic, and
why it is read twice.
