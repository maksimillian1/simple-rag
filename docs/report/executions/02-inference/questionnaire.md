# 02-inference — open decisions

## The largest open item in this report

**The contention pass never ran.** The cluster was torn down before it was scheduled. Every §3.7
finding (sustained rate, replica counts, no ceiling up to 1000 req/s) assumes an idle ingestion
path. It is unknown whether a concurrent backfill degrades the query path, either by competing
for the same TEI replicas or through Qdrant's upsert and optimizer work contending with search
reads on the same node. The answer settles an operational question, whether a backfill needs a
maintenance window or can run anytime, instead of refining a number. Provision a cluster just to
run this before treating the query-path results as final?

## Worth a real calibration run?

**Generation cost (`E18`, ~$0.51/1k queries) is derived and was never measured.** It is built
from the real prompt template (`apps/api/core/llm.go`), the real chunk size and `top_k`
(`apps/chunker/src/config.py`, `load.js`), and a Bedrock rate from the AWS Price List API. No run
called Bedrock, and the number is about 110x the marginal retrieval cost. That makes it the
largest line in the query-path cost and the one this report can least confirm. One run with real
generation, even a handful of requests, would make it a measurement. Do that before the number
goes into anything binding (a budget, a pricing page, a customer-facing figure)?

## Reference gap

**`methodology.md` is cited (§1 Sweep order: "two refinement points... `methodology.md` §7") and
does not exist in this repo.** Same gap as `01-ingestion`. Write it, or remove the citation.

## Housekeeping

**The 4 `data/*.point.md` files** (`r200`, `r300`, `r500`, `r1000`; `r050` has none) are the
script's per-point template output, and every one is unfilled: served rate, p95, error, cost and
saturation signal are blank. The real numbers are in `index.md`'s Matrix and Notes. Delete them,
or keep them as a record of what the tooling was supposed to produce?
