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

---

## Directory Structure
Look [Directory Structure](./docs/architecture.md#directory-structure)

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
