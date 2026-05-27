# 6: Two-Stage Hybrid Retrieval and Reranking Strategy

Date: 2026-05-26

## Status
Accepted

## Context
To achieve Enterprise-grade RAG precision, the query layer (`apps/api/` in Go) must retrieve documents that are both keyword-accurate and semantically relevant. Single-vector search often fails on exact keyword matches (IDs, product codes, specific terminology), while pure BM25 fails on conceptual intent.

We need a multi-stage retrieval and reranking pipeline optimized for execution latency, low memory footprint in the Go API, and zero external runtime dependencies.

### Constraints & Requirements
1. **Low Latency:** The synchronous query path must return results in <200ms.
2. **Resource Efficiency:** Avoid deploying heavy, resource-intensive cross-encoder reranking models (e.g., `bge-reranker-large`) on persistent GPU/CPU nodes to keep AWS infrastructure costs at zero for the query layer.

## Decision
We implement a lightweight, cost-efficient **Two-Stage Hybrid Retrieval and Reranking pipeline** directly within the Go API and Qdrant storage layer.

### Stage 1: Hybrid Retrieval & Custom Keyword Scaling
* **Implementation:** Execute a synchronized hybrid query against Qdrant utilizing its native Dense Vector Index (using the 384-dim `bge-small-en-v1.5` vectors) combined with Qdrant's Sparse Vector Index (for BM25-like keyword matching).
* **Word Count Match & Penalty Algorithm:** To prevent document spamming (where documents with artificially stuffed keywords manipulate the score), the Go API will apply a deterministic token-frequency penalty algorithm. If a keyword's frequency exceeds a statistical threshold within a specific chunk, its sparse weight is scaled down using a logarithmic dampening function:
  $$Score_{final} = Score_{raw} \times \frac{1}{\log_{10}(TermCount + 10)}$$

### Stage 2: Semantic Reranking (Reciprocal Rank Fusion - RRF)
* **Implementation:** Instead of using a heavy Cross-Encoder model that requires dedicated neural compute, we use **Reciprocal Rank Fusion (RRF)** to merge and rerank the dense and sparse result sets.
* **Justification:** RRF is a pure mathematical algorithm that executes in microseconds on the CPU within the Go API, providing a high quality boost by combining the best of both worlds without infrastructure overhead.

## Consequences

### What becomes easier:
* **Infrastructure Cost:** Zero extra dollars spent. No heavy reranker models running on persistent instances.
* **Performance:** Blazing fast execution in Go. Qdrant handles the heavy lifting of hybrid retrieval via gRPC.

### What becomes more difficult:
* **Algorithmic Tuning:** The Go API must maintain custom logic for RRF constants ($k=60$) and the keyword penalty dampening factor, requiring thorough unit testing.
