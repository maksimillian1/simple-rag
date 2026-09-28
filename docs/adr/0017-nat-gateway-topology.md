# ADR-0017: One NAT gateway per availability zone in production

Date: 2026-09-26

## Status

Accepted.

## Context

`single_nat_gateway = true` (`terraform/variables.tf`, the default) puts one NAT gateway in one
zone and routes all three private subnets through it. It was chosen on price: $37.96 a month
against $113.88 for three.

A NAT gateway is zonal and does not fail over. The private route tables name one gateway id, so
when its zone goes that route stays dead until a `terraform apply` builds a replacement elsewhere
and rewrites the tables. Nothing recovers on its own.

That would be a minor risk if NAT only carried traffic from pods already running. It also carries
image pulls from `quay.io`, `ghcr.io`, `docker.io` and `public.ecr.aws`; `ec2`, `ssm` and `pricing`
for Karpenter; `sqs` and `s3` for the ingestion path and its KEDA triggers; `sts` for every IRSA
token exchange; and `bedrock-runtime` for generation.

Node join is what settles it. Cilium is the CNI, aws-node having been replaced. A new node
registers with the EKS control plane over an in-VPC ENI and needs no NAT for that, then sits
`NotReady` until the Cilium agent pod pulls its image from `quay.io`. Without egress that pull
never finishes and nothing is scheduled onto the node.

Losing the NAT's zone therefore does not cost a third of the cluster. It freezes the whole cluster
at its current size, in the two healthy zones as well: running pods keep serving, nothing grows,
and nothing that dies comes back. §3.6 of the report measures this system scaling from 2 to 30
replicas under load, and that is the property that goes. Lose any other zone and egress survives,
so the exposure is one zone in three.

Removing the dependency instead of duplicating the gateway means all of: every image mirrored into
private ECR (pull-through cache covers quay.io, ghcr.io and docker.io, `public.ecr.aws` is global
and has to be copied); interface endpoints for `ecr.api` and `ecr.dkr`; an S3 gateway endpoint,
since ECR keeps layers in S3; interface endpoints for `sqs`, `ec2`, `sts`, `ssm` and `eks`; a
decision about `pricing:GetProducts`, which Karpenter uses to pick instances; and the Helm
repositories vendored, because `terraform apply` reaches them over the public internet. Five
interface endpoints is $131.40 a month before traffic, more than three gateways cost, and the last
item still leaves `terraform apply` internet-dependent.

So the choice is between one gateway and three, not between NAT and PrivateLink.

## Decision

1. Production runs `single_nat_gateway = false`. Three gateways and their two extra Elastic IPs
   cost $83.22 a month more, and the report carries it as a §5 guardrail.
2. That sits outside the right-sized floor rather than inside it. The right-sized column changes
   sizes and keeps the topology, and a gateway per zone is a topology change.
3. The variable keeps its `true` default, because the normal use of this repository is a cluster
   raised and torn down for one execution. Its description now says so, and production sets it in
   tfvars. Reading the default as production-ready is the mistake this record exists to stop.
4. Egress stays internet-dependent whatever the topology, since every image comes from a public
   registry. Per-zone gateways make that dependency zone-redundant, not absent, and no later
   decision should claim otherwise without doing the work listed above.

## Consequences

A zonal single point of failure for node join, image pulls and every AWS API the runtime touches is
now named and priced instead of hiding behind a variable default.

Development and production differ in a way that lives in tfvars and is invisible in the code, so a
capture from a dev cluster cannot be read as a production floor without saying which value was set.
The floor in this report was measured on a single gateway.

An S3 gateway endpoint is free and worth adding on its own merits. It is also missing today, while
`00-baseline` §2 claims S3 already leaves through one.

## References

`docs/report/report.md` §5; `docs/report/figures.yaml` (`nat_gateway_per_az`, `nat_ha_delta`,
`nat_ha_extra_ips`, `nat_ha_total`). Bedrock egress:
[ADR-0018](0018-bedrock-egress-transport.md). Code: `terraform/variables.tf`,
`terraform/modules/01-rag-core/modules/eks/vpc.tf`.
