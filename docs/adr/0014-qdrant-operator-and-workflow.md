# ADR-0014: Standardizing on KubeBlocks for Qdrant Lifecycle Automation and Data Protection

Date: 2026-06-29

## Status
Proposed

## Context
The system requires a highly available, sharded vector database deployment of Qdrant to support scalable RAG pipelines. While Qdrant offers an official enterprise operator for its Hybrid Cloud and Private Cloud products, utilizing it introduces commercial licensing overhead, external SaaS dependencies, and strict registration requirements (mandatory `customer-id` and `cluster-id` parameters synced with Qdrant Cloud Control Plane).

Conversely, maintaining a raw, vanilla `StatefulSet` deployment introduces substantial operational overhead. Managing complex database lifecycle tasks—such as day-2 automated backups to AWS S3, cross-Availability Zone node self-healing, automated failover orchestration, and seamless vertical/horizontal scaling—would require writing and maintaining custom `CronJob` manifests, shell scripts with AWS CLI dependencies, and brittle Kubernetes orchestration loops.

To minimize technical debt while retaining an entirely open-source, vendor-agnostic infrastructure plane, a unified and proven database orchestration layer must be standardized.

## Decision
We reject both the commercial Qdrant Hybrid Cloud Operator and the manual administration of vanilla `StatefulSet` manifests. We adopt **KubeBlocks** as the core database orchestration engine to manage the lifecycle of an open-source, Apache 2.0-licensed Qdrant deployment.

KubeBlocks will be leveraged as the platform primitives layer to manage the vector database based on the following architectural justifications:

### 1. Standardization of Day-2 Operations via Unified CRDs
* Instead of maintaining custom backup scripts, database backups, scheduling, and retention policies will be formalized using native KubeBlocks Custom Resource Definitions (`BackupPolicy` and `Backup`).
* Database operations such as horizontal scaling, vertical scaling, and version upgrades will be executed declaratively using the KubeBlocks `OpsRequest` CRD, eliminating custom migration risks.

### 2. Elimination of Commercial Vendor Lock-In
* KubeBlocks orchestrates the community-edition image of Qdrant (`qdrant/qdrant`). This eliminates the requirement to interface with external SaaS control planes, saving subscription costs and ensuring complete data plane isolation inside our EKS cluster.

### 3. Automated Failure Recovery (Auto-Healing)
* Unlike standard Kubernetes `StatefulSet` controllers that lack stateful topology awareness, KubeBlocks provides an advanced `InstanceSet` engine. It natively understands stateful cluster status and handles automated pod recovery, traffic redirection, and volume re-attachments during AWS Availability Zone disruptions or node terminations without data corruption.

### 4. Integration with Cloud Object Storage
* Long-term data durability will be achieved by connecting KubeBlocks directly to an isolated AWS S3 bucket. Backups will be triggered via API-level snapshots natively supported by Qdrant and offloaded off-cluster using KubeBlocks storage providers.

## Consequences
* **Positive:** Complete automation of Qdrant clustering, backups, and restores using a unified, production-grade open-source operator. Zero licensing fees and zero external platform dependencies. Reduced operations engineering overhead.
* **Negative:** Introduces KubeBlocks CRDs and its core operator lifecycle as an additional cluster-wide dependency that must be maintained and updated within the cluster engine plane.
* **Mitigation:** KubeBlocks will be isolated in its own dedicated namespace and bundled as a core cluster-add-on module inside the GitOps repository, decoupled from the application-plane workloads.
