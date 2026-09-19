# 02 · Inference — query path — Concepts

Mechanisms only. Values are in `index.md`. Cited from outside as `02-inference/K1`.

## K1 · Generation is stubbed, so every latency here describes retrieval

Calling Bedrock would bend the curve where the provider's quota throttles rather than where the
cluster runs out. The delay is fixed rather than removed because an instant stub frees handlers
faster than production ever would, and low rather than realistic because a generous one would
hide the retrieval ceiling.

**Consequence** — that no p95 here is an end-to-end SLO, and that comparing it to the design
target in `architecture.md` compares two different quantities.

## K2 · The autoscaler is under test, so replicas are an output

Nothing inside the cluster is edited between points: work arrives only when the generator sends
it, so at low rates a ceiling of ten and a ceiling of fifty both produce two replicas. Ceilings
are raised out of reach, and scaler and node convergence sit inside the point because production
requests arrive at whatever capacity exists at that moment.

**Consequence** — a replica column and no replica axis, a point discarded if it hits its ceiling,
and both replica guardrails read from the sustained rate.

## K3 · The sustained rate is set by the latency target, not the throughput ceiling

An open-loop generator past capacity queues its own excess, and the measured p95 then grows with
run length rather than describing the system. The sweep climbs from below and stops at the last
rate holding the target, guarded by served rate matching offered and errors near zero.

*Overload is a different question, answered by served rate and status codes rather than a percentile.*

**Consequence** — where the grid stops, and why no throughput figure here is quoted without its
latency condition.

## K4 · Token cost and byte cost diverge by three orders of magnitude

A generated answer is priced by tokens and carried by bytes. `E18`'s 2,312<!--FD117--> tokens cost $0.000509<!--FD118--> ᴱ
to generate and weigh roughly 9 KB, so whatever moves them — NAT processing or a PrivateLink
endpoint — bills about a tenth of a percent of what generating them bills. The ingestion path
inverts it: documents are carried, nothing is generated, and NAT is 62.8% of the marginal total
in the one run with a CUR actual.

**Consequence** — that no network-topology choice on the query path is settled on cost, and that
`D22`'s crossover is reported as a range rather than a value.
