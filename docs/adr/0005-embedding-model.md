# 5: Embedding Model Selection and Decoupled Service Architecture

Date: 2026-05-26

## Status

Accepted

## Context

The `simple-rag` ingestion pipeline processes unstructured documents (PDF, TXT, Markdown) and requires an embedding model to convert text chunks into vectors before upserting them into the Qdrant VectorDB. Concurrently, the synchronous Go API query path requires real-time query vectorization to perform hybrid dense/sparse search retrieval in Qdrant.

To satisfy both the asynchronous ingestion pipeline and the synchronous query path, the embedding layer is deployed as a centralized, dedicated HuggingFace TEI (Text Embeddings Inference) service.

This architecture satisfies the following core operational requirements:

* **Global Accessibility:** The embedding service exposes centralized gRPC/HTTP endpoints, making it simultaneously accessible to the synchronous `Go API` (for low-latency search queries) and the ephemeral `indexer` workers (for batch document chunks).
* **Predictable Autoscaling (KEDA):** The service scales dynamically using KEDA based on the internal model queue depth (`tei_queue_size`). This decouples scaling from raw CPU/Memory metrics, preventing cold-start latency spikes during ingestion bursts while efficiently handling user search traffic.
* **Resource Efficiency & Throughput:** Centralizing the TEI deployment enables server-side dynamic batching. It pools concurrent single queries from the search API and bulk requests from the ingestion workers into unified batches, maximizing GPU/CPU utilization and system throughput.
* **Infrastructure Simplification:** A standalone service eliminates the need to bundle, maintain, and duplicate heavy model containers inside multiple application pods. This simplifies the container footprint across all environments, including local development.

## Decision

We adopt **`BAAI/bge-small-en-v1.5`** as the default embedding model and deploy HuggingFace TEI as a **decoupled, shared Kubernetes Service** rather than a co-located sidecar.

To satisfy the system design, we enforce the following implementation mandates:

1. **Shared Deployment Model:** The TEI container runs in its own Kubernetes deployment, exposing an HTTP/gRPC interface accessible within the cluster.
2**KEDA Scaling on Request Metrics:** The standalone TEI deployment scales dynamically via a KEDA scaler monitoring queue depth metrics (`tei_queue_size`).
3**Vector Database Optimization:** The model outputs a **384-dimensional vector**, minimizing Qdrant's RAM usage for HNSW indexing.
4**CI/CD Model Baking:** The 130MB model weights remain baked directly into the TEI Docker image to eliminate HuggingFace Hub downloads at runtime.

## Consequences

### What becomes easier:
* **Synchronous Query Vectorization:** The Go API can easily query the shared TEI service endpoint to vectorize search queries, completing the hybrid retrieval flow.
* **Simplified Job Pods:** The `indexer` is simplified into a single-container job, reducing RAM and scheduling overhead per K8s Job.
* **Independent Scalability:** Embedding compute power (CPU/GPU nodes) scales independently of the SQS message queues based on actual inference demand.

### What becomes more difficult / Risks:
* **Network Overhead:** Ingestion now requires internal cluster network calls between the `indexer` and the shared TEI service (instead of zero-network overhead localhost loopback). This is mitigated by keeping both services within the private VPC subnet boundary.
* **Complex Infrastructure Tracking:** Introducing a separate TEI deployment adds another KEDA autoscaler configuration, which must be tuned to prevent cold starts when handling sudden ingestion bursts.
* **Strict Language Lock-in:** `bge-small-en-v1.5` remains English-only.

