# ADR-0016: Dedicated Database Nodes and Topographical Isolation

Date: 2026-07-13

## Status

Accepted

## Context

As the platform scales, we are planning to integrate `simple-rag` with a comprehensive observability stack (Prometheus, Grafana, and related telemetry agents). This stack is responsible for processing, storing, and visualizing metrics during peak loads. Observability tools, particularly Prometheus during high-volume metric scraping intervals, can exhibit significant and sudden spikes in CPU and Memory usage.

If the stateful Vector Database (Qdrant) is deployed onto the same shared "Tier 2: On-Demand Managed Pool" nodes as these infrastructure daemons (as originally outlined in ADR-0010), it becomes highly susceptible to the "Noisy Neighbor" problem. A severe spike in observability processing could lead to resource starvation for Qdrant, resulting in degraded query performance, increased latency, or worst-case scenarios like the Vector Database Pod being forcefully terminated (OOMKilled) by the Kubernetes scheduler.

To maintain stringent reliability and SLA guarantees for retrieval operations, the stateful database tier must be physically isolated from other platform workloads.

## Decision

We will amend the cluster topology to provision an explicitly isolated, dedicated tier of EKS Managed Nodes specifically for the Qdrant Database.

1. **Dedicated Infrastructure Provisioning (Terraform):**
   * We will provision a new EKS Managed Node Group (`eks_database_nodes`) scoped strictly to `t3.large` instances to comfortably accommodate the Vector DB's memory requirements alongside the baseline DaemonSets.

2. **Strict Scheduling Boundaries:**
   * **Taints and Tolerations:** The new database nodes will be tainted with `dedicated=database:NO_SCHEDULE`. This prevents any generic platform components, API deployments, or observability agents (like Prometheus) from scheduling onto this compute tier.
   * **Labels and Node Selectors:** The database nodes will be labeled with `tier=database`. The Qdrant `kubeblocks` cluster configuration will be explicitly pinned to these nodes via a `nodeSelector` matching the label, and it will feature corresponding `tolerations` to bypass the node taint.

3. **Resource Entitlement:**
   * The Qdrant workloads will be configured with larger, guaranteed resource `requests` (e.g., 1 CPU, 4Gi Memory) and `limits` (e.g., 2 CPU, 6Gi Memory) that fully utilize the dedicated `t3.large` capacity without fear of CPU throttling or memory starvation from external workloads.

## Consequences

* **Positive - Blast Radius Mitigation:** Prometheus/Grafana and other platform daemons can freely utilize their assigned shared nodes aggressively during peak loads without impacting the performance or stability of production database queries.
* **Positive - High Availability:** Complete elimination of the risk of the database being OOM-killed due to unpredictable behavior of sibling pods on a shared node.
* **Negative - Financial Baseline Cost:** Provisioning a dedicated managed node group strictly for the database introduces a permanently elevated baseline cost (EC2 footprint) regardless of database utilization levels, as the nodes cannot be densely packed with other workloads.
* **Negative - Sub-optimal Packing:** Node resources that are not explicitly consumed by the database (or core system DaemonSets) will remain idle.
