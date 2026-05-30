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
* `terraform/`        -> Infrastructure as Code (Strict tagging: `app = "simple-rag"`, see Section 5)

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
* **Local Ingestion Testing Strategy (AWS Native):** Run code locally by targeting real AWS S3 and SQS test infrastructure. To enforce security boundaries without code changes, applications must pod-mount or host-read standard AWS shared configuration profiles (`~/.aws/credentials`). The app code must rely strictly on standard AWS SDK environment variables (`AWS_PROFILE`, `AWS_REGION`). Do not implement mock endpoints, local state emulators, or alternative local cloud provider software.
* **Data Contracts Compliance:** Every schema validation, SQS JSON payload, and HTTP request/response structure must perfectly map to the explicit formats and tokenization/indexing guardrails defined in `docs/contracts.md`.

## 5. Terraform Infrastructure-as-Code (IaC) Rules & Best Practices
You must strictly adhere to these practices when writing or modifying any Terraform configuration:
* **Mandatory Resource Tagging Policy:** Every AWS resource that supports metadata tags MUST be explicitly configured with the following tag definitions:
  - `app          = "simple-rag"` (Grouping project identification)
  - `environment  = var.environment` (e.g. `"local-test"`, `"staging"`, or `"prod"`)
  - `managed-by   = "terraform"` (Identifying management layer)
* **Standardized Suffixes & Collisons Protection:**
  - Resource names must prefix or suffix their logical identifiers using dynamic prefix variables like `${var.resource_prefix}` or local variables to isolate test stacks.
  - S3 buckets must utilize `random_id` dynamic suffix generation to avoid global naming collisions.
* **Security & Resource Boundaries:**
  - **Public Access Blocks:** All S3 buckets must be coupled with an explicit, strict `aws_s3_bucket_public_access_block` configuration with all blocking fields set to `true`.
  - **No Hardcoded Secrets:** Credentials, AWS Access Keys, or Account IDs must never be checked into git or written directly in provider blocks. Always rely on standard profile references or the default credential chains.
  - **Dead-Letter Queues (DLQs):** All primary message queues (SQS) must declare a redrive policy routing failing messages to a sibling `-dlq` queue with reasonable `maxReceiveCount` limit (e.g. 3).
  - **Least Privilege Access Policies:** Queue policies (`aws_sqs_queue_policy`) must define narrow conditions limiting permissions specifically to source bucket ARNs using conditional operators like `ArnEquals`.
