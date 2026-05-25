# 2. Vector Storage Selection for RAG Pipeline

Date: 2026-05-23

## Status

Accepted

## Context

Our RAG pipeline requires a vector database capable of executing low-latency similarity searches (p95 < 30ms) while maintaining high throughput (QPS > 800).
The infrastructure strategy mandates deployment inside a Kubernetes cluster with tight memory boundaries (4–8 GB baseline RAM for the staging/testing phase).

We evaluated five core options based on market benchmarks: Qdrant, Milvus, Weaviate, Pinecone (Serverless), and pgvector.

The key constraints are:
1. **Infrastructure ROI**: SaaS solutions (Pinecone) provide zero architectural leverage in case experienced cloud/DevOps engineer exists.
2. **Resource Footprint**: Complex distributed systems (Milvus) require heavy external dependencies (etcd, Pulsar, MinIO), violating our lean infrastructure goal.
3. **Filtering Performance**: The database must support metadata filtering without massive QPS degradation.

## Decision

We have decided to select **Qdrant (Self-hosted via Helm in Kubernetes)** as our primary Vector Database.

Why Qdrant:
1. **Performance to Efficiency Ratio**: Outperforms competitors with a p95 latency of 15–25ms and handles up to 1200 QPS on comparable hardware.
2. **Advanced Memory Optimization**: Supports native Scalar Quantization (SQ) and Product Quantization (PQ), reducing raw RAM consumption by ~75% (from 90-100GB down to 22-25GB per 100M vectors), enabling deployment within strict Kubernetes resource limits.
3. **Cloud-Native Architecture**: Written in Rust, provides an official Helm chart/Operator, and exposes native Prometheus metrics out of the box, aligning perfectly with our Cilium network topology and observability stack.
4. **No Filtering Degradation**: Uses single-stage filtering, avoiding the performance drops seen in Weaviate or Pinecone when combining vector search with payload metadata filters.

## Consequences

* **Stateful Management**: Since Qdrant is self-hosted in K8s, we must manage storage persistence using AWS EBS (gp3) CSI driver and define robust backup strategies (snapshots).
* **Quantization Trade-offs**: Enabling Scalar Quantization to save RAM introduces a negligible drop in search precision (Recall), which must be benchmarked during the PoC phase.
* **Operational Ownership**: The team (you) is fully responsible for cluster scaling, Raft consensus stability, and resource sizing, rather than offloading it to a third-party vendor.
