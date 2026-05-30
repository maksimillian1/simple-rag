# ==============================================================================
# Gemini Code Assist Context: simple-rag (Strict Guardrails & Architecture V2)
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
* `deploy/k8s/`       -> Kubernetes manifests (KEDA ScaledJobs, Cilium NetworkPolicies, ServiceAccounts)
* `docs/`             -> System documentation (`architecture.md`, `contracts.md`, `ops.md`)
* `terraform/`        -> Infrastructure as Code (Strict AWS EKS, IAM IRSA, SQS, S3 provision)

## 3. Rigid Architectural References & SDK Guardrails
All implementation details, data routing, and infrastructure limitations are governed strictly by `docs/architecture.md`. You must enforce the following rules:

* **Single Source of Truth (SSoT):** Adhere exclusively to the lifecycle, diagrams, and components defined in `docs/architecture.md`.
* **Mandatory Haystack 2.0 Integration (Strict Limit):** You are STRICTLY FORBIDDEN from writing raw HTTP requests (via `requests`, `httpx`, or `urllib3`) to the TEI sidecar, and you MUST NOT use the low-level `qdrant_client` directly for document ingestion or point structure generation. Both `chunker` and `indexer` MUST exclusively use the **Haystack 2.0 Pipeline architecture**. Use native components like `TEIDocumentEmbedder` and `QdrantDocumentWriter` from `qdrant-haystack`. Custom vector operations (such as token hashing or Sparse Vector generation) must be injected into Haystack `Document` objects before running the pipeline.
* **Runtime Profiles (Zero-Daemon vs Dev Mode):**
  - **Production Environment (`ENVIRONMENT=prod`):** The applications operate under the **Zero-Daemon Operational Profile** controlled by KEDA ScaledJobs. The python worker process MUST process messages in a tight loop and immediately self-terminate (`exit 0`) the moment the SQS queue returns empty. Do not implement `time.sleep` or continuous waiting loops in production.
  - **Development Environment (`ENVIRONMENT=dev`):** To ease local testing without emulating KEDA components, the worker loop must check the `CONTINUOUS_POLL` environment variable. If `ENVIRONMENT=dev` and `CONTINUOUS_POLL=true`, the application is allowed to enter a local continuous polling mode, sleeping for a defined interval when the queue is empty, instead of exiting. This execution path must be explicitly guarded by environment checks.
* **Stage 2 Pod Multi-Container Pattern:** The `indexer` application never computes dense embeddings locally. It must offload all tensor inference to the colocated **TEI Sidecar** via `localhost:8080` using `BAAI/bge-small-en-v1.5` integrated into the Haystack pipeline.
* **Idempotency Strategy:** The `indexer` must generate deterministic point IDs for Qdrant using `UUID5(file_name + chunk_index)` to ensure flawless AWS Spot resiliency.
* **Query Layer Logic:** The Go API (`apps/api/`) must strictly implement the Two-Stage Hybrid Retrieval, the specific **Word Count Token-Frequency Penalty Formula**, and **Reciprocal Rank Fusion (RRF with $k=60$)** detailed in the architecture guide.
* **Security & IAM (IRSA Compliance):** Absolutely zero hardcoded AWS Access Keys or `.env` files with credentials. Production code relies entirely on standard AWS Credential Provider Chain. Kubernetes pods use IAM Roles for Service Accounts (IRSA) via WebIdentity token projection. Local code must let `boto3`/Go SDK resolve native AWS shared config profiles (`~/.aws/credentials`) transparently.
* **Kubernetes Memory Optimization Strategy:** All Python applications must adhere strictly to a **Lazy-Loading Pattern**. Framework components (e.g., Haystack `Pipeline`, `QdrantDocumentWriter`, `boto3`) must be imported and initialized dynamically only after a message is successfully pulled or when the application initializes its runtime components.

## 4. Terraform & Kubernetes Co-existence & IaC Architecture Rules
When generating or interacting with infrastructure configuration or deployment manifests, you must strictly comply with these enterprise design principles:

* **Separation of Concerns (Terraform vs K8s Boundary):**
  - Terraform (`terraform/`) is strictly restricted to provisioning cloud infrastructure foundational state: VPC, EKS cluster, managed node groups, SQS queues, S3 buckets, and IAM Roles.
  - You are STRICTLY FORBIDDEN from using Terraform to manage Kubernetes application payloads. Do not use `kubernetes_manifest`, `kubernetes_pod`, or `helm_release` inside Terraform modules to deploy `simple-rag` services. All K8s manifests, KEDA ScaledJobs, and K8s ServiceAccounts must be isolated strictly inside `deploy/k8s/`.
* **IRSA (IAM Roles for Service Accounts) Tight Coupling:**
  - For every cloud resource requiring access (S3, SQS), Terraform must export the AWS IAM Role ARN featuring an explicit Trust Policy bound to the EKS Cluster OIDC Provider (`oidc.eks.<region>.amazonaws.com/id/...`).
  - The corresponding Kubernetes manifest in `deploy/k8s/service-account.yaml` must explicitly declare the annotation `eks.amazonaws.com/role-arn: <IAM_ROLE_ARN>` to bind the runtime pod security context natively.
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

## 5. Current Phase & Engineering Tasks
* **Phase:** Local PoC / Ingestion Integration V2 (Transitioning to Haystack 2.0 Pipelines & K8s Preparation).
* **Task 1 (Refactoring Apps):** Refactor `apps/chunker/` and `apps/indexer/` to drop manual HTTP/client boilerplate and migrate fully to declarative Haystack 2.0 Pipelines.
* **Task 2 (Dev Environment Branching):** Update the core execution loop in `main.py` for both apps to cleanly split execution logic based on the `ENVIRONMENT` variable:
  - If `dev` and `CONTINUOUS_POLL=true` -> log notice and loop indefinitely with sleep interval.
  - If `prod` or queue drained in default state -> log metric and issue immediate `exit 0`.
* **Task 3 (K8s ServiceAccount & IRSA Specs):** Prepare standard manifests in `deploy/k8s/` that expect IRSA injection, aligning permissions with the explicit SQS and S3 topologies.
* **Data Contracts Compliance:** Every schema validation and SQS JSON payload must perfectly map to the explicit formats defined in `docs/contracts.md`.
