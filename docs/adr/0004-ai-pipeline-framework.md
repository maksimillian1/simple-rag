# 5: AI Pipeline Framework Selection and Embedded Inference Model

Date: 2026-05-26

## Status
Accepted

## Context
The `simple-rag` ingestion pipeline utilizes event-driven Kubernetes ScaledJobs (via KEDA) deployed on AWS Spot Instances. The primary operational metrics are predictability, deployment simplicity, and a deterministic processing rate (`chunks/job/sec`).

We need to choose an orchestration framework and an embedding generation strategy. While a decoupled microservice architecture (external inference cluster) provides high scalability, it introduces network dependencies, complex multi-component deployments, and variable intra-cluster latency during the MVP phase.

### Evaluated Alternatives
1. **Monolithic Frameworks (LangChain/LlamaIndex):** Rejected due to massive dependency trees, slow Python startup times, and high baseline memory footprints (>1.5GB RAM before processing data).
2. **Decoupled Architecture (Remote TEI Cluster):** Deferred. Introduces infrastructure overhead (persistent deployments, load balancers, service mesh) that complicates initial deployment and horizontal scaling configuration.
3. **Embedded In-Job Inference via Haystack 2.0:** Accepted. Combines a lean orchestration graph with local, deterministic CPU-bound embedding generation inside the transient K8s Job context.

## Decision
We adopt **Haystack 2.0** as the pipeline orchestration framework and enforce an **Embedded Local Inference** model using the lightweight `all-MiniLM-L6-v2` model running directly on CPU within the `indexer` K8s Job.

To guarantee execution predictability and mitigate Python/Model startup latency on AWS Spot infrastructure, we enforce the following engineering constraints:

### 1. Hardcoded Local Model Baking (CI/CD Mandate)
* **Anti-Pattern:** Downloading the embedding model at runtime from HuggingFace Hub or mounting it via AWS EFS is strictly prohibited.
* **Implementation:** The `all-MiniLM-L6-v2` model weights must be downloaded during the Docker image build phase and baked directly into the container storage layer. The Haystack `SentenceTransformersTextEmbedder` must be configured with a local path to eliminate external network calls during Job initialization.

### 2. Strict Resource Allocation Profiles
* **Memory Limits:** Individual `indexer` ScaledJobs must be bound to a hard Kubernetes resource limit of **2GB RAM**.
* **Execution Predictability:** By baking the 90MB model directly into the image, container startup (Cold Start) is decoupled from network speed. Throughput (`chunks/job/sec`) becomes a direct, predictable function of the allocated K8s CPU shares.

### 3. Pipeline Lifecycle Management
* **Explicit Teardown:** Upon completing the SQS payload processing loop, the Python script must explicitly invoke `gc.collect()` and clear the embedding pipeline cache from memory before the K8s Job container exits with code 0.

## Consequences

### Positive
* **Zero External Dependencies:** The `indexer` job is fully self-contained. If SQS and Qdrant are up, the indexer works.
* **Deterministic Scaling:** KEDA scales the K8s Jobs based strictly on SQS queue depth, with zero risk of cascading failures or overloading a shared inference endpoint.
* **Simplified Infrastructure:** No need to maintain, patch, or scale a separate persistent inference deployment.

### Negative / Risks
* **Increased Image Size:** The final Docker image increases by ~100MB (model weights), resulting in a slight increase in K8s container registry pull times if image caching is not optimized on EKS nodes.
* **Horizontal Scaling Limits:** Scaling is tied to EKS node compute limits. Massive scale-ups will require larger or more numerous CPU-optimized AWS Spot instances.
