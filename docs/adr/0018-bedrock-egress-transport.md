# ADR-0018: Remove the Bedrock VPC endpoints

Date: 2026-09-28

## Status

Accepted. Supersedes clause 2 of the Decision in
[ADR-0007](0007-llm-selection-aws-bedrock.md), "Zero-Internet Network Egress (FinOps & SecOps)".
The model, the IRSA authentication and the prompt format are unchanged.

## Context

ADR-0007 routed Bedrock through a PrivateLink endpoint for two reasons in one sentence: it
"enforces an absolute data privacy boundary" and it "slashes NAT Gateway data processing charges".
The privacy boundary was the architectural point. The saving was what made it easy to accept, on
the assumption that a per-gigabyte rate five times under NAT's would repay the fixed cost quickly.
Nobody worked out the break-even.

An endpoint costs $26.28 a month for three ENIs whatever happens, and charges $0.010/GB against
NAT's $0.052/GB. It repays that fixed cost above $26.28 / ($0.052 − $0.010) = 625.71 GB a month. A
query weighs 12,248 bytes on the wire (`02-inference/E18`, `K4`), so break-even is 54,854,311
queries a month. This system is designed and measured against 1,000,000. At that volume the network
costs $0.59 via NAT and $26.39 via the endpoint, against $508.64 of generation tokens either way.

So the endpoint costs 45 times the path it was meant to relieve, the crossover sits 55 times above
the design volume, and transport is 0.12% of the token bill. There was no financial case here in
either direction once the numbers existed.

The privacy boundary was never in effect either. Both endpoints were created in `eu-central-1`
while the client calls `us-east-1`: `MODEL_ID` is `us.meta.llama3-1-8b-instruct-v1:0`, a
cross-region inference profile, and `AWS_BEDROCK_REGION` is `us-east-1`. Private DNS for a
eu-central-1 endpoint never matches a us-east-1 hostname, so generation has been resolving to the
public endpoint and leaving through NAT all along. The Cilium policy admits
`bedrock-runtime.*.amazonaws.com`, a wildcard over every region, which is what let that pass
unnoticed. The second endpoint, `bedrock`, is the control plane and nothing can reach it: no
control-plane SDK in `go.mod`, IAM grants only `InvokeModel*`.

Two endpoints, $52.56 a month, no boundary and no saving.

## Decision

1. Delete both endpoints from `module.vpc_endpoints`, with the security group that existed only for
   them. Generation egresses through NAT like every other AWS call here.
2. Both halves of ADR-0007 clause 2 are withdrawn: the cost claim as measured false, the privacy
   claim as not worth $26.28 a month at this volume and threat model.
3. No claim that customer documents stay inside the VPC perimeter may appear in this repository.
   Traffic to Bedrock is protected by TLS and IAM, which is weaker and true.
4. Narrow the Cilium `matchPattern` to the region actually called. With the endpoints gone this
   policy is the only egress control left. Not yet applied: no run has called Bedrock for real, so
   a stricter rule would fail closed on the first real request with nothing to verify it against.
5. Reopen this on cost if a workload approaches 54 million queries a month, or on security if a
   data-residency obligation appears. The first real generation run replaces the three estimates
   behind the break-even.

## Consequences

Chunks of customer documents will cross the public internet to reach Bedrock. That is the content
of this decision. Under a residency obligation it would be the wrong call, and such an obligation
appearing is the trigger to reopen it. `AWS_BEDROCK_REGION` is `us-east-1` with a cross-region
profile, so generation leaves Europe anyway; removing the endpoint only takes away the last piece
of infrastructure that implied otherwise.

The right-sized fixed floor falls by $52.56: Block B to $411.31, Block C to $737.74, and §5's
budget alarm to $575.84. NAT data processing now carries generation, $0.59 a month at the reference
volume.

## References

`docs/report/report.md` §4.5; `docs/report/figures.yaml` (`endpoint_breakeven_queries`,
`vpc_endpoints`, `vpc_endpoint_control_plane`). NAT topology: [ADR-0017](0017-nat-gateway-topology.md).
Code: `terraform/modules/01-rag-core/modules/eks/vpc.tf`,
`deploy/k8s/apps/api/network-policy.yaml`.
