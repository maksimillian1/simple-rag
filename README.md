# Simple RAG Pipeline

A highly cost-efficient, production-ready document indexing and RAG (Retrieval-Augmented Generation) pipeline deployed on AWS. The project's architecture is strictly built around a **Zero-Daemon policy** for ingestion: the indexing components never run continuously. Instead, they are spun up as short-lived, ephemeral Kubernetes Jobs only when load is present, driving idle infrastructure costs down to absolute zero.

---

## Core Architecture

The system relies on an event-driven flow that automatically scales out via KEDA based on the volume of incoming documents. AWS S3 acts as the strict **Data Ingestion Window**—external systems drop files into S3, creating a decoupled, asynchronous interface.

Look [Architecture Diagram](./docs/architecture.md#data-flow-diagram)

## Key constraints:
Embedding model must be 384 dimensions to minimize Qdrant RAM usage.
Chunk size is 512 tokens max, prod range should be 256–384 tokens to balance context retention and vector quality.
Single sqs message could have chunks of single file with upper size limit of 256KB, which is the max SQS message size.


### Architectural Deep-Dives (ADR Log)
For specific design justifications, performance baselines, and cost optimization trade-offs, consult the official Architecture Decision Records matching the current repository state:

* [ADR-0001: System Boundaries & Core Components](./docs/adr/0001-system-boundaries.md)
* [ADR-0002: Vector Storage Selection](./docs/adr/0002-vector-storage.md)
* [ADR-0003: SQS Payloads](./docs/adr/0003-sqs-payloads)
* [ADR-0004: AI Pipeline Framework Selection](./docs/adr/0004-ai-pipeline-framework.md)
* [ADR-0005: Embedding Model Selection](./docs/adr/0005-embedding-model.md)
* [ADR-0006: Hybrid Retrieval and Reranking](./docs/adr/0006-retrieval-with-reranking.md)
* [ADR-0007: LLM Selection for Context Post-Processing](./docs/adr/0007-llm-selection-aws-bedrock)
* [ADR-0012: Advanced Query Configuration Approach](./docs/adr/0012-advanced-query-configuration-approach.md)

---

## Directory Structure
Look [Directory Structure](./docs/architecture.md#directory-structure)

---

## Advanced Query Configuration

The API avoids opinionated guardrails and code-level clamping for query parameters where it's not make sense (see [ADR-0012](./docs/adr/0012-advanced-query-configuration-approach.md)). This means developers have raw control over retrieval tuning.

### Hybrid Mode & `poolAlpha`
In hybrid retrieval mode, the `poolAlpha` parameter balances the weighting and prefetch limits between Dense (Semantic) and Sparse (Keyword) results.

* **Standard Hybrid (`0.0 < poolAlpha < 1.0`):** Distributes the prefetch limit according to the ratio. For example, `poolAlpha = 0.5` pulls an equal number of candidates from both indexes before applying Reciprocal Rank Fusion (RRF).
* **Extreme Values (`0.0` or `1.0`):** Setting `poolAlpha` to exact boundaries is explicitly allowed. 
  * `poolAlpha = 0.0` allocates a `0` prefetch limit to the Dense query, effectively turning the request into a **Pure Sparse** search.
  * `poolAlpha = 1.0` allocates a `0` prefetch limit to the Sparse query, turning the request into a **Pure Dense** search.
  
**Expected Behavior:** While setting `poolAlpha` to boundary values logically contradicts "hybridness," the system will not throw validation errors or artificially enforce minimum limits. It will execute exactly as configured. This pushes the responsibility of mathematically sound configuration to the caller while minimizing code bloat in the API layer.

---

## Integration Modes

The architecture is explicitly built to support dual deployment topologies depending on your product scale:

1. **Standalone RAG Service:** Operates as an isolated, dedicated ingestion and semantic retrieval system with its own Go API gateway.
2. **Pluggable System Module:**
  * **Terraform Level:** The entire infrastructure footprint can be imported as a Git module into an existing enterprise VPC topology.
  * **Kubernetes Level:** Ingestion workloads and the VectorDB deploy natively into dedicated namespaces within an existing shared EKS cluster, utilizing IAM Roles for Service Accounts (IRSA) for zero-credential security.

## Development and ADR Tooling

Architectural changes must be peer-reviewed via the `adr-tools` standard before executing any code changes.

* **Initialize new design record:** `adr new "Your Decision Title"`
* **Supersede an existing policy:** `adr new -supersedes 0004 "Migrating Framework"`

## Setup

### Terraform
* terraform init
* terraform apply

### Kubernetes
* aws eks update-kubeconfig --region eu-central-1 --name simple-rag-cluster

### Argo CD
To trigger an update
* kubectl patch application root-bootstrap -n argocd --type merge -p '{"operation": {"sync": {"revision": "HEAD"}}}'
