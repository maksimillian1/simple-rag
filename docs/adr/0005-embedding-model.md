# 5: Embedding Model Selection for Local Inference

Date: 2026-05-26

## Status

Accepted

## Context

The `simple-rag` ingestion pipeline processes unstructured documents (PDF, TXT, Markdown) and requires an embedding model to convert text chunks into vectors before upserting them into Qdrant VectorDB.

The architecture enforces an embedded, in-job inference model running strictly on CPU instances within ephemeral Kubernetes ScaledJobs (via KEDA) on AWS Spot infrastructure. This environment introduces tight operational constraints:
1. **Memory Ceiling:** Individual `indexer` jobs have a hard resource limit of 2GB RAM.
2. **Cold Start Cost:** Downloading model weights from external registries (HuggingFace Hub) at runtime or over slow network mounts (AWS EFS) eliminates AWS Spot cost-efficiency due to CPU idle time.
3. **Retrieval Quality (Business Driver):** Low-quality search retrieval leads to poor RAG outputs, which carries a severe penalty for Enterprise-grade applications. We cannot use outdated or poorly performing models just because they are lightweight.

## Decision

We adopt **`BAAI/bge-small-en-v1.5`** as the default embedding model for the `simple-rag` baseline pipeline.

To satisfy the context constraints, we enforce the following implementation mandates:

1. **CI/CD Model Baking:** The 130MB model weights must be downloaded during the Docker image build phase and baked directly into the `apps/indexer/` container layer. The Haystack execution context must load the model locally, guaranteeing zero external network dependencies during Job execution.
2. **Acceptance of Resource Overhead:** We explicitly accept a ~40% increase in model size and computational footprint compared to `all-MiniLM-L6-v2` (~90MB). This trade-off is justified by the significant upgrade in retrieval quality (MTEB score), which directly correlates with business value.
3. **Vector Database Optimization:** The model outputs a **384-dimensional vector**. This size is optimal as it minimizes Qdrant's RAM usage for HNSW indexing, keeping VectorDB compute costs flat.
4. **Decoupled Evaluation Strategy:** The codebase must wrap the embedding execution behind a Strategy Pattern. This ensures we can easily run future automated retrieval evaluation pipelines (e.g., A/B testing with LLM-as-a-Judge) to justify the cost-to-quality ROI of heavier models versus lighter baselines.

## Consequences

### What becomes easier:
* **Production Reliability:** Baking the model into the container makes `indexer` throughput (`chunks/job/sec`) completely deterministic and bound only to allocated CPU shares.
* **Vector DB Cost Control:** Sticking to 384 dimensions prevents RAM bloat in Qdrant, allowing the database to scale cheaply on standard AWS compute nodes.
* **Search Precision:** High baseline accuracy on English-language documents right out of the box.

### What becomes more difficult / Risks:
* **Image Delivery Overhead:** The final Docker image size increases by ~130MB. This must be mitigated by optimizing EKS node image caching (e.g., using pre-warmed AMI or large EBS volumes) to ensure fast KEDA scale-ups.
* **Strict Language Lock-in:** `bge-small-en-v1.5` supports English only. Processing multilingual documents (e.g., Russian text) will result in complete garbage vectors. Swapping to a multilingual model (like `multilingual-e5-small`) is deferred to Phase 2 and will require a full database re-indexing.
