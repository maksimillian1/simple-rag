# ADR-0014: Ingress Traffic Topography via Cilium eBPF Gateway API and Cluster Traffic Policy

Date: 2026-06-29

## Status

Proposed

## Context

To expose the synchronous query path (`apps/api`) to external consumers under the 4-Tier Compute Architecture defined in `ADR-0010`, we require a high-performance, secure L4/L7 ingress routing infrastructure. Conventional Kubernetes architectures rely on AWS Application Load Balancers (ALB) coupled with in-cluster Nginx Ingress controllers, which introduces redundant reverse-proxy layers, inflates latency profiles, and increases maintenance TCO.

Furthermore, we must prevent external network traffic from traversing or consuming computational resources on sensitive node tiers, specifically the `system-core` pool (hosting the Qdrant Vector DB) and the `apps-compute` pool (hosting ephemeral KEDA batch jobs). We need to evaluate the optimal Kubernetes `externalTrafficPolicy` to balance traffic evenly across the serving tier without compromising compute boundaries.

## Decision

We reject legacy Ingress Controller stacks and standard cloud-provider L7 load balancing. Instead, we mandate the deployment of the **Cilium eBPF Gateway API Engine** utilizing an AWS Network Load Balancer (NLB) combined with a **`Cluster` External Traffic Policy**.

The network routing architecture is strictly governed by the following operational mandates:

### 1. Unified eBPF L4/L7 Edge Routing (AWS NLB + Cilium Gateway)
* External ingress termination is offloaded to an AWS Network Load Balancer (NLB) operating strictly at L4, provisioned automatically via the Cilium Gateway Class inside the public subnet perimeter.
* The NLB bypasses HTTP parsing and routes raw TCP streams directly to the private `apps-serving` EC2 instances. L7 routing, TLS termination, and path-matching are executed inside the Linux kernel's socket layer via Cilium’s eBPF/XDP fabric, eliminating reverse-proxy user-space overhead.

### 2. Enforcement of `Cluster` Traffic Policy over `Local`
We explicitly enforce `externalTrafficPolicy: Cluster` for the Ingress Gateway service, rejecting the `Local` configuration due to structural tradeoffs within our dynamic scaling model:
* **Blast Radius Protection:** Network isolation is achieved via strict AWS target-group scope constraints. The AWS NLB is configured to register nodes *exclusively* from the `apps-serving` pool. User-facing traffic is physically barred from entering the network interfaces of `system-core` or `apps-compute` nodes.
* **Mitigation of Traffic Imbalance:** Under uneven scaling conditions (e.g., KEDA scaling the Go API to 3 replicas across 2 physical nodes), the `Cluster` policy ensures that the internal eBPF mesh cross-routes packets to achieve perfectly symmetric load distribution per pod. This eliminates the resource starvation risks inherent to the `Local` policy’s un-aware L4 node balancing.
* **Operational Stability during Disruption:** During rapid Karpenter consolidation cycles or active rolling deployments, the `Cluster` policy allows the network layer to remain stable. The NLB target group does not experience aggressive flap intervals (Healthy/Unhealthy cycles), preventing connection drop windows for active clients.

```
 [ External Client Request ]
              │
              ▼
    ┌───────────────────┐
    │  AWS L4 NLB (Pub) │
    └───────────────────┘
              │  Routes strictly to Serving Tier
              ▼
 ┌────────────────────────────────────────────────────────┐
 │ Tier 3: apps-serving Node Pool (Private Subnet)        │
 │                                                        │
 │  ┌───────────────┐  eBPF Redirect  ┌───────────────┐   │
 │  │    Node-A     │────────────────>│    Node-B     │   │
 │  │ (No API Pod)  │                 │  (Go API Pod) │   │
 │  └───────────────┘                 └───────────────┘   │
 └────────────────────────────────────────────────────────┘
         │                                       │
         X Denied by Cilium NetPol               X Denied by Cilium NetPol
         ▼                                       ▼
 ┌──────────────────────────────┐        ┌──────────────────────────────┐
 │ Tier 2: system-core Pool     │        │ Tier 4: apps-compute Pool    │
 │ (Qdrant Vector DB / ArgoCD)  │        │ (Chunker / Indexer Jobs)     │
 └──────────────────────────────┘        └──────────────────────────────┘
```

## Consequences

* **Symmetric Ingress Performance:** The Go API replicas receive a uniform distribution of user queries, optimizing CPU utilization and securing predictable p95 processing metrics (<200ms).
* **Absolute Tier Isolation:** Core cluster systems and transient data-ingestion jobs are completely insulated from public network traversal. Cilium `CiliumNetworkPolicy` matrices reinforce this at Layer 4, dropping any unauthorized intra-cluster hops attempting to bridge into non-serving namespaces.
* **Micro-Overhead Acceptability:** We accept the minor latency premium introduced by occasional eBPF-driven inter-node hops within the internal private network mesh, as Cilium eliminates iptables lookup tables, making the execution speed acceptable under our strict SLA targets.
* **Streamlined Load Balancer Config:** Terraform configuration profiles for the AWS NLB target groups are simplified, eliminating complex, low-threshold health check configurations required to handle rapid `Local` policy node state mutations.
