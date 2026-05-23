# Simple RAG Pipeline

A highly cost-efficient, production-ready document indexing and RAG (Retrieval-Augmented Generation) pipeline deployed on AWS. The project's architecture is strictly built around a Zero-Daemon policy: the indexing component never runs continuously. Instead, it is spun up as a short-lived Kubernetes Job only when real load is present, driving infrastructure costs down to the absolute minimum.

## Architecture

The system relies on an event-driven flow that automatically scales out based on the volume of incoming documents.


The architecture treats AWS S3 not just as storage, but as the strict **Data Ingestion Window**.
External systems do not call our internal APIs to index files; they drop documents into the designated S3 prefix. This forms a decoupled, file-based asynchronous interface (Contract) that guarantees zero runtime dependencies between the producer and the RAG pipeline.

For deep-dives into specific architectural definitions and trade-offs, refer to the official ADRs (Architecture Decision Records):


* [ADR-0001: System Boundaries & Core Components](./docs/adr/0001-system-boundaries.md) — Explains the event-driven ingestion via SQS/KEDA and query flows.
* [ADR-0002: Vector Storage Selection](./docs/adr/0002-vector-storage.md) — Decisions regarding DB scaling and indexing performance.
* [ADR-0003: Text Embeddings](./docs/adr/0003-embedding-model.md) — Strategy on model selection and abstraction layers.

```mermaid
graph TD
    User([User]) -->|Uploads Document| S3[AWS S3 Bucket]
    S3 -->|Object Created Event| SQS[AWS SQS Queue]
    SQS -->|Queue Metrics| KEDA[KEDA Scaler]
    KEDA -->|Triggers Spikes| Job[Kubernetes Job: Python Indexer]
    SQS -->|Consumes Message| Job
    Job -->|Parsing & Embeddings| VDB[(Vector DB)]
    
    User -->|Queries / Dashboards| API[Go API]
    API -->|Retrieves Context| VDB
    
    style S3 fill:#f9f,stroke:#333,stroke-width:2px
    style SQS fill:#bbf,stroke:#333,stroke-width:2px
    style Job fill:#bfb,stroke:#333,stroke-width:2px
```

### Infrastructure Isolation
Network security and resource boundaries are enforced via Cilium Network Policies and Kubernetes ResourceQuotas. Configuration baselines can be tuned in the default [values.yaml](./TODO).

### Standalone App vs. Pluggable Module

A major advantage of this architecture is its flexibility in how it integrates with your product ecosystem. It is designed to support two primary deployment modes:

- **Standalone RAG Application:** It can be run entirely on its own as a dedicated, fully self-contained document indexing and retrieval service.
- **Pluggable Module for Larger Systems:** The entire pipeline can be plugged directly into an existing, larger application ecosystem:
  - **Terraform Level:** The entire infrastructure footprint can be imported and declared as a modular sub-component within an existing Terraform codebase of a larger product, aligning with the host system's existing VPC and networking.
  - **Kubernetes Level (Kube Level):** The API service and the event-driven indexing workloads can be easily deployed as a modular namespace or microservice within an existing Kubernetes cluster, integrating natively with other applications sharing the cluster.

## Directory Structure

This repository is organized as a strict monorepo layout. Do not introduce alternative root-level folders:

```text
simple-rag/
├── apps/
│   ├── api/          # Lightweight Go-based API for frontend charts and querying
│   └── indexer/      # Python + Haystack pipeline (Short-lived Kube Job)
├── deploy/
│   └── k8s/          # Kubernetes manifests & KEDA ScaledObject configurations
├── docs/
│   └── adr/          # Architecture Decision Records log
└── terraform/
    ├── envs/prod/    # Environment entry point (invokes modules)
    └── modules/      # Reusable infrastructure (vpc, eks, iam_irsa, s3, sqs)
```

### Architecture Decision Records (ADR)

All architectural and infrastructure decisions are version-controlled inside the repository as Markdown files using the `adr-tools` standard from this [repo]('https://github.com/npryce/adr-tools'). This enforces peer-reviewed design before code execution.

* **Create new ADR:** `adr new "Selecting Vector Database"`
* **Supersede old ADR:** `adr new -supersedes 0002 "Migrating to Alternative VectorDB"`
