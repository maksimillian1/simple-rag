# ADR-0015: Qdrant Clustering Topology, Operator Elimination, and Recovery Strategy

Date: 2026-07-13

## Status
Accepted

## Context
The system requires a highly available, sharded vector database deployment of Qdrant to support scalable RAG pipelines. We evaluated multiple orchestration strategies to manage database lifecycle, automated backups, and cross-AZ resilience.

Key requirements:
1. Zero commercial vendor lock-in or mandatory SaaS registration planes.
2. Minimal platform overhead (no unnecessary operator bloat).
3. Native support for multi-AZ high availability and automated disaster recovery.

## Decision
We reject both commercial operators (Qdrant Hybrid Cloud Operator) and multi-database operators (KubeBlocks).

We adopt a **vanilla Kubernetes StatefulSet architecture** using Qdrant's native Raft consensus mechanism, coupled with a dual-layer backup strategy (Velero + Native API Snapshots).

### 1. StatefulSet Topology and Peer-to-Peer Clustering
* **Helm-first Deployment:** Deployed using the official community Helm chart (`replicaCount: 2`).
* **Headless Service Discovery:** Pod discovery operates via Kubernetes Headless Service (`clusterIP: None`).
* **Internal Consensus:** Inter-pod communication and Raft consensus execute natively over gRPC port `6335`.
* **Multi-AZ Resilience:** Multi-AZ scheduling enforced via `topologySpreadConstraints` across dedicated database nodes.

### 2. Infrastructure & Application Backup Strategy
* **Velero & EBS CSI (Crash-Consistent):** Daily volume-level snapshots via AWS EBS CSI for total cluster disaster recovery.
* **CronJob API Snapshots (Application-Consistent):** A lightweight, native `CronJob` triggers Qdrant REST API snapshots (`POST /collections/{collection_name}/snapshots`) and offloads `.snapshot` files directly to an isolated AWS S3 bucket using IAM Roles for Service Accounts (IRSA).

---

## Considered Options & Trade-Offs

### Option 1: Official Qdrant Hybrid Cloud Operator
* **Why Rejected:** Introduces commercial licensing overhead, SaaS control plane dependencies, and mandatory registration parameters (`customer-id`, `cluster-id`).

### Option 2: KubeBlocks Database Orchestrator
* **Why Rejected:**
    1. *Version Lock-in:* The KubeBlocks controller strictly limits the supported Qdrant engine versions, lagging behind upstream releases and blocking crucial features (e.g., scalar quantization optimizations).
    2. *Platform Bloat:* Enforces the installation of unused database CRDs, metrics agents, and extra sidecars, violating our minimalist infrastructure principles.

### Option 3: Standard StatefulSet + Native Clustering (Selected)
* **Pros:** Leverages Qdrant's built-in Raft consensus protocol, drastically reduces cluster CRDs, ensures access to zero-day upstream Qdrant releases, and utilizes standard open-source tools (Velero/S3).
* **Cons:** Requires explicit maintenance of the custom snapshot CronJob manifest.

---

## Consequences
* **Positive:** Clean architecture without external operator overhead, zero licensing costs, instant access to Qdrant updates, resilient multi-AZ database clustering.
* **Negative:** Operational responsibility for database lifecycle (upgrades, scale-outs) relies on standard GitOps procedures rather than CRD-driven automation.
