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

## K2 · The autoscaler is under test, so replicas are an output

**One line** — nothing inside the cluster is edited between points, the scaler decides how much
capacity appears, and the replica count is read afterwards rather than set beforehand.

Raising a replica ceiling does not raise throughput on this path. Work arrives only when a
client sends it, so at a low arrival rate no pod is under pressure, the scaler sees nothing to
react to, and a ceiling of ten and a ceiling of fifty produce the same two replicas. That is the
structural difference from the ingestion path, where the whole corpus is already queued and any
extra worker is consumed immediately. There, a ceiling is the only ingestion ractive; here it is
inert until something else forces the system against it.

The ceiling is therefore raised out of reach deliberately, and a point that reaches it is
discarded rather than reported. A run pinned at its maximum has measured a number someone typed
into a manifest, and the shape of the curve past that point is a property of the manifest.

Convergence belongs inside the point for the same reason. A production request arrives at
whatever capacity exists at that moment, and how long the scaler takes to add more is part of
what the deployment can promise. Starting the measurement window before replicas and nodes have
settled mixes scale-out latency into the steady-state p95; starting it after, but recording how
long settling took, keeps both numbers and confuses neither. Node provisioning sits inside that
interval too, and on a mixed pool it is the slower half.

The cost side follows the same logic. Replicas and nodes move with the axis, so the serving bill
moves with it, and the marginal cost of a query is a real measured quantity rather than a floor
divided by throughput. What must be removed from it is the always-on minimum, which exists at
zero traffic and belongs to the floor.

**Consequence** — why the matrix has a replica column and no replica axis, which points are
valid, and where both replica guardrails come from.

## K3 · The sustained rate is defined by the latency target, not by the throughput ceiling

**One line** — pushing the generator past capacity produces a larger throughput number and a
meaningless latency number, so the sweep stops at the last rate the system serves inside its
target.

An open-loop generator sends at a fixed rate whether or not the system keeps up. Once arrivals
exceed service capacity, the excess queues ahead of the system and every subsequent request
waits behind the whole backlog. The measured p95 then grows with the length of the run: a
five-minute overload and a fifty-minute overload at the same rate report different latencies for
the same configuration. The number describes the queue, not the machine.

The sweep therefore climbs from below and stops at the last rate that holds the target with
errors near zero. Two readings guard it at every point. The served rate must match the offered
rate, or the generator was the limit and the point says nothing about the system. The error rate
must stay near zero, because a rate sustained by rejecting requests is not sustained.

Overload has a legitimate use, and it is a different question with different instruments: does
the system degrade or collapse when traffic exceeds capacity. That is answered with served rate
and status codes rather than with a latency percentile, and it is not part of this execution.

**Consequence** — where the grid stops, which two columns invalidate a point, and why no
throughput figure in this report is quoted without its latency condition.
