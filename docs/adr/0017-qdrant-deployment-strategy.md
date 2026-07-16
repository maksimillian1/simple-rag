# ADR-0017: Qdrant Clustering Topology, Operator Elimination, and Recovery Strategy

Date: 2026-07-15

## Status

Accepted

## Context

Following the integration of the KubeBlocks operator for Qdrant vector database management, several critical operational bottlenecks were identified during staging evaluation:
1. **Version Lock-in and Lag:** The KubeBlocks controller strictly limits the Qdrant engine version, lagging significantly behind upstream releases and blocking required features (e.g., specific scalar quantization optimizations).
2. **Platform Bloat:** The operator enforces the installation of unused database engines, custom CRDs, and telemetry sidecars, violating our minimalist infrastructure principle.
3. **Enterprise Paywalls:** Advanced backup, clustering, and recovery operations in alternative custom operators (such as the official hybrid operator) require commercial licensing, which is incompatible with our open-source, self-hosted deployment target.

At the same time, we must guarantee high availability (HA), automated snapshots, and complete disaster recovery (DR) capabilities for our retrieval-augmented generation pipeline.

Because Qdrant features a mature, built-in cloud-native clustering engine based on the Raft consensus protocol, we do not require a dedicated operator inside the cluster to manage state, data replication, or node discovery.

## Decision

We will completely decommission and remove the KubeBlocks operator and implement a pure Kubernetes StatefulSet architecture coupled with a dual-layer backup strategy:

### 1. StatefulSet Topology and Peer-to-Peer Clustering
* **Helm-first Deployment:** We will deploy Qdrant using the official, community-maintained Helm chart, configured to generate a standard `StatefulSet` with `replicaCount: 3`.
* **Headless Service Discovery:** Node discovery will be managed via a Kubernetes Headless Service (`clusterIP: None`). Upon startup, each Qdrant pod will resolve the headless service DNS (`qdrant-headless`) to obtain peer IPs.
* **Internal Consensus:** Inter-pod communication and Raft consensus will run natively over the dedicated gRPC port `6335` without external dependencies.
* **Topology Spread Constraints:** We will enforce multi-AZ scheduling using `topologySpreadConstraints` (or `podAntiAffinity`) to ensure pods are distributed across different AWS Availability Zones on our dedicated database nodes (configured in ADR-0016).

### 2. Infrastructure-Level Recovery (Velero & EBS CSI)
* **Crash-Consistent Volume Backups:** We will utilize Velero to orchestrate daily snapshots of the persistent volumes (`gp3` storage class managed via the AWS EBS CSI driver).
* **StatefulSet Recreation:** Velero will backup both the persistent disk state and the Kubernetes resource manifests (StatefulSet, Service, PVC, ConfigMaps). In a total disaster scenario (e.g., AZ blackout), Velero will recreate the exact database topology and attach the restored EBS volumes natively.

### 3. Application-Level Backup (CronJob API Snapshots)
* **Automated API-Level Snapshots:** To guarantee application-level, crash-safe data consistency, we will deploy a lightweight Kubernetes `CronJob` that executes daily.
* **Snapshot Trigger Pipeline:**
    1. The CronJob container authenticates via IAM IRSA to obtain permissions for our secure AWS S3 Backup Bucket.
    2. It triggers the Qdrant REST API (`POST /collections/{collection_name}/snapshots`) to force Qdrant to flush its write-ahead log (WAL) to disk and create a consistent `.snapshot` file.
    3. The CronJob downloads the snapshot file and streams it directly to the remote S3 bucket, applying a 30-day retention lifecycle policy.
