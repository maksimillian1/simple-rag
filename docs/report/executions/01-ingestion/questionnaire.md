# 01-ingestion — open decisions

## Worth spending more cluster time on?

**`D29` (Fargate break-even for ingestion) is still not computed.** The rate is no longer the
blocker: a real `eu-central-1` Fargate rate is in `00-baseline/data/price-2026-09-09.json`. The
pod-hours are. `M12`'s split gives dollars per workload rather than raw CPU and memory
pod-hours, and the Matrix's `N reached` column covers only the indexer's time-weighted
concurrency. The chunker's was never captured at that precision; all that exists is "peaked ~20,
had headroom". Finishing D29 needs a fresh run on a live cluster that records the chunker's
time-weighted concurrency at each N. Worth it, or is Spot versus Fargate for this workload not
worth re-provisioning for?

## Reference gap

**`methodology.md` is cited by name (§7, in the Axis section, and in `D24`'s formula note) and
does not exist in this repo.** Every citation points nowhere. Either write it (it is cited for the
coarse-to-fine sweep-order rule and for "floor lines excluded by definition"), or remove the
citations and inline a one-line version of each rule.

## Not a decision, just a flag

**N=10's cost ($41,624/1M docs) rests on one run.** The report reads it as genuine low-N
economics rather than a corrupted point, and that reading survives two different ways of
dividing the NAT data. It is still a single data point. Only a second, independent N=10 run
(impossible now, the cluster is gone) would move it from "plausibly correct" to "confirmed". If
the number ends up load-bearing somewhere, give it the confidence one run supports.
