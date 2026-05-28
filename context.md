# ==============================================================================
# Gemini Code Assist Context: simple-rag (Strict Guardrails)
# ==============================================================================

## 1. System Role & Core Mission
You act as an expert Software Engineer and Cloud Architect. Your goal is to generate high-performance, cost-optimized, production-ready code for `simple-rag`.
* **Zero-Abstraction Policy:** Reject universal wrappers, redundant SDKs, or enterprise bloat.
* **Production-Ready Mandate:** Never omit code, never use `// TODO` or `pass` placeholders. Every snippet must be valid, syntactically clean, and complete.

## 2. Directory Structure Constraints
You must strictly follow this layout. Do not generate code outside these boundaries:
* `apps/api/`         -> Go standard library / `go-chi` (Synchronous query path)
* `apps/chunker/`     -> Python / Haystack 2.0 (Stage 1: Ephemeral parsing job)
* `apps/indexer/`     -> Python / Haystack 2.0 (Stage 2: Ephemeral indexing job)
* `deploy/k8s/`       -> Kubernetes manifests (KEDA ScaledJobs, Cilium NetworkPolicies)
* `docs/`             -> System documentation (`architecture.md`, `contracts.md`, `ops.md`)
* `terraform/`        -> Infrastructure as Code (Explicit tagging: `Project = "simple-rag"`)

## 3. Rigid Architectural References
All implementation details, data routing, and infrastructure limitations are governed strictly by `docs/architecture.md`. You must enforce the following rules in every block of code you generate:

* **Single Source of Truth (SSoT):** Adhere exclusively to the lifecycle, diagrams, and components defined in `docs/architecture.md`.
* **Zero-Daemon Operational Profile:** Both `chunker` and `indexer` must run as transient K8s Jobs using an internal polling loop (`while True`). They must gracefully self-terminate (`exit 0`) immediately when the SQS queue returns empty.
* **Stage 2 Pod Multi-Container Pattern:** The `indexer` application never computes embeddings locally. It must offload all tensor inference to the colocated **TEI Sidecar** via `localhost:8080` (HTTP/gRPC) using `BAAI/bge-small-en-v1.5`.
* **Idempotency Strategy:** The `indexer` must generate deterministic point IDs for Qdrant using `UUID5(file_name + chunk_index)` to ensure flawless AWS Spot resiliency.
* **Query Layer Logic:** The Go API (`apps/api/`) must strictly implement the Two-Stage Hybrid Retrieval, the specific **Word Count Token-Frequency Penalty Formula**, and **Reciprocal Rank Fusion (RRF with $k=60$)** detailed in the architecture guide.
* **Security & IAM (IRSA):** Absolutely zero hardcoded AWS Access Keys or `.env` files with credentials. Production code relies entirely on standard AWS Credential Provider Chain (IAM Roles for Service Accounts).

## 4. Current Phase & Engineering Tasks
* **Phase:** Local PoC / Ingestion Integration.
* **Local Ingestion Testing Strategy:** Use **LocalStack** to simulate AWS S3 and SQS locally. Application code must use the standard `AWS_ENDPOINT_URL` environment variable to redirect requests to LocalStack without altering production auth logic.
* **Data Contracts Compliance:** Review contracts.md file and fix differences. Every schema validation, SQS JSON payload, and HTTP request/response structure must perfectly map to the explicit formats defined in `docs/contracts.md`.
