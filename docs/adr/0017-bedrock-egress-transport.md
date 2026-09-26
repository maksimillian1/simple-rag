# ADR-0017: Bedrock Egress Transport — PrivateLink on Privacy, Not on Cost

Date: 2026-09-26

## Status

Accepted. Supersedes clause 2 of the Decision in [ADR-0007](0007-llm-selection-aws-bedrock.md)
("Zero-Internet Network Egress (FinOps & SecOps)") in its cost reasoning only. The generative
engine, the IRSA authentication model and the prompting standard of ADR-0007 stand unchanged, and
so does the intent to keep generation traffic off the public internet.

## Context

ADR-0007 justified routing Bedrock traffic through an interface VPC endpoint on two grounds: it
"enforces an absolute data privacy boundary" and it "slashes NAT Gateway data processing charges".
The first is sound. The second was never measured, and measurement now contradicts it by more than
an order of magnitude. This ADR records the calculation so the decision is made on the reason that
survives, and pins what remains broken rather than leaving it in prose.

### The calculation

Rates, eu-central-1, from the Price List API and our own CUR rows (`docs/report/figures.yaml`):

| | NAT gateway | Interface endpoint |
| :--- | ---: | ---: |
| Fixed | $0.052/h, one gateway | $0.012/h per ENI, one ENI per AZ |
| Fixed per month | $37.96 | $26.28 (3 AZ) |
| Per gigabyte | $0.052 | $0.010 |

The endpoint's per-gigabyte rate is 5.2x cheaper, so it repays its own fixed cost only above a
traffic volume. That volume is $26.28 / ($0.052 - $0.010) = **625.71 GB per month**.

A query weighs 12,248 bytes on the wire (2,312 tokens at an estimated 4 bytes per token plus
request overhead; `02-inference/E18`, `K4`). The break-even is therefore **54,854,311 queries per
month**. The reference volume this report is written against is 1,000,000. At that volume:

| | Via NAT | Via the endpoint |
| :--- | ---: | ---: |
| Network | $0.59 | $26.39 |
| Generation (Bedrock tokens) | $508.64 | $508.64 |
| Network as a share of generation | 0.12% | 5.2% |

The endpoint is **45x more expensive** at the reference volume, and the crossover sits 55x above
it. Transport is not a cost argument on this path in either direction: at 0.12% of generation,
the whole question is rounding against the token bill. Every byte figure is an estimate and no run
has yet called Bedrock for real; `02-inference/K4` carries the assumptions and their biases, and
`docs/tech-debt.md` #9 is the run that would replace all three at once.

### What the endpoint is actually worth

Against the alternative, the endpoint buys three things NAT cannot:

1. **The traffic never leaves the AWS network.** Document chunks reach the model without crossing
   the public internet. This is ADR-0007's compliance argument and it is the one that holds.
2. **An endpoint policy.** An interface endpoint carries a resource policy that restricts
   principals, actions and models at the network layer. NAT has no equivalent: with NAT the only
   controls are IAM and the Cilium FQDN policy, both of which sit elsewhere and can drift apart.
3. **Availability that matches the topology.** The endpoint has one ENI per AZ. The NAT gateway is
   a single zonal resource and this deployment runs `single_nat_gateway = true`
   (`terraform/variables.tf`, default, not overridden), so all three private subnets egress through
   one AZ. Losing that AZ stops every outbound flow — SQS polling, image pulls, Bedrock — while the
   2/2/2 node topology across three AZs keeps running. Matching NAT to the topology means three
   gateways, $113.88/month against $37.96, which is +$75.92 — three times the endpoint it would be
   replacing.

### What NAT is good enough at

Throughput and latency are not the concern. A NAT gateway scales from 5 to 100 Gbps; the heaviest
point in the inference campaign (`r1000`, 828 req/s served) moved about 45 GB in four hours, near
26 Mbps average — three orders of magnitude below the bottom of that range. The 1,000,000-query
reference moves 11.4 GB per month in total.

Two NAT limits are real but unmeasured here, since no run has called Bedrock for real: AWS caps
simultaneous connections at 55,000 per unique destination tuple, which a high-concurrency
generation path with short-lived connections could approach; and with a single gateway two of the
three AZs pay a cross-AZ hop on every outbound byte, already visible as the "Other cross-AZ" line
in the idle floor.

### What is broken as deployed

The privacy boundary is not in effect today, for a reason that has nothing to do with cost. Both
endpoints are created in `eu-central-1` (`vpc.tf`, `module.vpc_endpoints`), while the client calls
`us-east-1`: `MODEL_ID` is `us.meta.llama3-1-8b-instruct-v1:0`, whose `us.` prefix is a
cross-region inference profile, and `AWS_BEDROCK_REGION` is set to `us-east-1`
(`deploy/k8s/apps/api/deployment.yaml`). Private DNS for a eu-central-1 endpoint never matches a
us-east-1 hostname, so a real generation call would resolve to the public endpoint and leave
through NAT — the transport ADR-0007 forbids. The Cilium egress policy admits
`bedrock-runtime.*.amazonaws.com`, a wildcard across every region, which is what lets this pass
silently and is also the control a data-residency review would ask about first.

Separately, the `bedrock` control-plane endpoint is provisioned and billed and is reachable by
nothing: `apps/api/go.mod` carries no control-plane SDK, IAM grants only `InvokeModel*`, and the
egress policy admits only `bedrock-runtime.*`. It costs $26.28/month for no function.

So the deployment currently pays $52.56/month for two endpoints and obtains neither the privacy
boundary nor a cost saving.

## Decision

1. **The endpoint is justified by the privacy boundary and by AZ-independent egress, not by cost.**
   Any future argument for or against it is made on those grounds. The FinOps half of ADR-0007
   clause 2 is withdrawn.
2. **Keep the `bedrock-runtime` endpoint. Delete the `bedrock` control-plane endpoint.** It is a
   defect, not a sizing choice, and is already carried as `docs/tech-debt.md` #12.
3. **Align the endpoint with the region actually invoked**, either by serving a model in
   `eu-central-1` or by moving the endpoint to the invoked region. Until that holds, the privacy
   boundary this ADR rests on is declared not in effect.
4. **Narrow the Cilium `matchPattern`** from `bedrock-runtime.*.amazonaws.com` to the single region
   chosen in 3, so that a regional drift fails closed instead of silently egressing.
5. **Do not fund a per-AZ NAT on this argument.** At +$75.92/month against a $26.28 endpoint, the
   endpoint is the cheaper way to make Bedrock egress AZ-independent. The single NAT remains a
   declared single point of failure for every other outbound flow, recorded here rather than
   resolved.
6. **Re-derive the crossover after the first real generation run.** The byte weight behind
   54,854,311 queries rests on three estimates (`02-inference/K4`); one measured run replaces them.

## Consequences

### What becomes easier

* The decision now rests on a claim that survives measurement, so a reader who checks the bill does
  not find the rationale contradicted by it.
* The cost of the privacy boundary is stated as a number rather than implied to be a saving: about
  $26 per month at any volume this system will see, against a generation bill two orders of
  magnitude larger.
* Items 2-4 are a closed list with an acceptance test, which is what `docs/tech-debt.md` #12 tracks.

### What becomes more difficult / Risks

* This ADR pins debt rather than clearing it. Until item 3 lands, ADR-0007's compliance claim and
  this one are both aspirational, and any statement that customer documents stay inside the VPC
  perimeter is not true of the running system.
* Choosing a model served in `eu-central-1` may mean a different model than Llama 3.1 8B Instruct,
  which would reopen ADR-0007's primary decision rather than only its transport clause.
* The calculation above is estimated end to end on the byte side. If the real token-to-byte ratio
  is materially higher than 4 bytes per token, the crossover moves down, though it would have to
  move by more than a factor of fifty to reach the reference volume.

## References

* Measurement and figures: `docs/report/report.md` §4.5, `docs/report/figures.yaml`
  (`endpoint_breakeven_queries`, `endpoint_at_ref_queries`, `nat_at_ref_queries`,
  `vpc_endpoint_control_plane`)
* Debt and acceptance test: `docs/tech-debt.md` #12, #9
* Code: `terraform/modules/01-rag-core/modules/eks/vpc.tf`,
  `deploy/k8s/apps/api/deployment.yaml`, `deploy/k8s/apps/api/network-policy.yaml`
