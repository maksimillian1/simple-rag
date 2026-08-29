# 02 · Inference — query path — Concepts

Mechanisms only. Values are in `index.md`, cited by block. Refs are cited from outside as
`02-inference/K1`.

## K1 · Generation is stubbed, and that decides what the latency number means

**One line** — the Go API returns a canned completion after a fixed delay instead of calling
Bedrock, which makes every latency figure here a statement about retrieval and about nothing
downstream of it.

Bedrock is a managed service behind an account-level quota. A rate sweep that calls it stops
being a measurement of this configuration once the quota starts shaping the response times: the
curve then bends where the provider throttles, not where the cluster runs out of capacity. The
components under test are the Go API, TEI and Qdrant, and all three sit upstream of the
generation call. Removing the call removes a source of variance that belongs to someone else's
infrastructure, and it removes a token bill for runs whose purpose is to saturate the machine.

The delay is fixed rather than absent for a different reason. An instant stub frees each request
handler as soon as retrieval finishes, so connections return to the pool and goroutines unwind
faster than they ever would in production. Concurrency in flight stays low, the resources that
would run out first never run out, and the sweep reports a sustained rate the deployed system
cannot hold. Holding each request open for a realistic interval keeps that pressure present
without making the pressure depend on an external service.

The delay is also chosen low rather than realistic. A generous stub would dominate the p95 and
hide the retrieval ceiling the execution exists to find. That trade is deliberate: the number
this execution produces is a retrieval-path capacity, and it is not the end-to-end latency a
user experiences. Comparing it against a design target written for the full path — the figure in
`architecture.md` — compares two different quantities, and the report says so where it makes the
comparison.

**Consequence** — what every p95 in this execution describes, whether the sustained rate
survives contact with real request lifetimes, and whether the headline can be quoted as an SLO.
