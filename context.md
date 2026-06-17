# ==============================================================================
# Gemini Code Assist Context: simple-rag (Strict Guardrails & Architecture V2.2)
# ==============================================================================

## 1. System Role & Core Mission
You act as an expert Software Engineer and Cloud Architect. Your goal is to generate high-performance, cost-optimized, production-ready code for `simple-rag`.
* **Zero-Abstraction Policy:** Reject universal wrappers, redundant SDKs, or enterprise bloat.
* **Production-Ready Mandate:** Never omit code, never use `// TODO` or `pass` placeholders. Every snippet must be valid, syntactically clean, and complete.

## 2. Directory Structure Constraints
You must strictly follow this layout. Do not generate code outside these boundaries:
* `apps/api/`         -> Go standard library / `labstack/echo` (Synchronous query path)
* `apps/chunker/`     -> Python / Haystack 2.0 (Stage 1: Ephemeral parsing job)
* `apps/indexer/`     -> Python / Haystack 2.0 (Stage 2: Ephemeral indexing job)
* `deploy/k8s/`       -> Kubernetes manifests (KEDA ScaledJobs, Cilium NetworkPolicies, ServiceAccounts)
* `docs/`             -> System documentation (`architecture.md`, `contracts.md`, `ops.md`)
* `terraform/`        -> Infrastructure as Code (Strict AWS EKS, IAM IRSA, SQS, S3 provision)

## 3. Interaction Protocol & Review-Optimized Output
* **No Wall of Code:** Generating the entire file is prohibited if the changes affect less than 50% of the code. Use the "Diff/Patch" pattern or show specific functions.
* **Explain the "Why":** Before the code, the model should explain the architectural decision (why this particular pattern/library) in 2-3 lines (bullet points).
* **Cognitive Load Reduction:** Absolutely no comments, section headers, or inline explanations are allowed in Terraform, configuration files, Go, or Python files. Code must be entirely self-documenting. Comments are permitted ONLY for documenting mathematically complex algorithms (e.g., the RRF formula) that cannot be inferred from standard API calls.
* **Draft Mode by Default:** If the task is complex, first propose the high-level design (pseudocode or function signatures) and wait for approval, instead of generating 200 lines of Python/Go code.
* **Strict Function Length & SRP:** The maximum size of any function or method is 50 lines of execution code (excluding decorators and docstrings). You must decompose logic into pure, single-purpose, easily testable functions adhering to the Single Responsibility Principle.
* **Magic Numbers & Configuration Guardrail:** Hardcoding configuration strings, regular expressions, salt values, or mathematical constants directly inside function bodies is strictly forbidden. All such values must be declared as top-level module constants (`UPPER_CASE`) or loaded via environment variables/Pydantic settings. Linear indices (0, 1) and empty initializers are allowed in-place.

## 4. Rigid Architectural References & SDK Guardrails
All implementation details, data routing, and infrastructure limitations are governed strictly by `docs/architecture.md`. You must enforce the following rules:
* **Single Source of Truth (SSoT):** Adhere exclusively to the lifecycle, diagrams, and components defined in `docs/architecture.md`.
* **Mandatory Haystack 2.0 Integration (Strict Limit):** Writing raw HTTP requests (via `requests`, `httpx`, or `urllib3`) to the TEI service is STRICTLY FORBIDDEN. You MUST NOT use the low-level `qdrant_client` directly for document ingestion or point structure generation. Both `chunker` and `indexer` MUST exclusively use the **Haystack 2.0 Pipeline architecture**.
* **Native Component Injection Rule:** Any custom logic (such as token hashing, ID generation, or Sparse Vector calculation) **MUST NOT** exist as standalone procedural functions. They must be encapsulated natively into custom Haystack components (`@component`) and linked explicitly inside the `Pipeline()` engine before execution, mapping inputs directly to Haystack `Document` objects.
* **Go API Framework & Non-Destructive Migration:** The `apps/api/` layer uses the `labstack/echo` framework. When modifying or optimizing the Go API, **do not rewrite existing working endpoints or routers from scratch** unless explicitly requested. Apply surgical modifications, keeping existing `go-chi` interfaces intact if they are not part of the active task, or gracefully adapt them to `echo.Context` without breaking the contract.
* **Zero-Daemon / Continuous Poll Strategy:** Both `chunker` and `indexer` must run as Python applications supporting dual execution modes governed by the `CONTINUOUS_POLL` environment variable:
  - **Dev Mode (local / local-test):** If `CONTINUOUS_POLL` is `True`, the worker loops continuously, sleeping 5 seconds on an empty queue and then polling again.
  - **Prod Mode (Kubernetes Jobs):** If `CONTINUOUS_POLL` is `False` or omitted, the worker must gracefully break the loop and self-terminate (`exit 0`) immediately when the SQS queue returns empty, enabling KEDA to scale down the transient job cleanly.
* **Stage 2 Pod Ingestion Pipeline (Haystack 2.0):** The `indexer` application must be built natively using declarative Haystack 2.0 Ingestion Pipelines. It must connect `TEIDocumentEmbedder` (which offloads dense embedding generation to the shared **TEI Service** using `BAAI/bge-small-en-v1.5`) and `QdrantDocumentWriter`. SQS chunks are mapped to native Haystack `Document` objects with custom `sparse_embedding` weights generated using the SPLADE model (`prithivida/Splade_PP_en_v1`).
* **Idempotency Strategy:** The `indexer` must generate deterministic point IDs for Qdrant using `UUID5(file_name + chunk_index)` to ensure flawless AWS Spot resiliency.
* **Query Layer Logic:** The Go API (`apps/api/`) must strictly implement the Two-Stage Hybrid Retrieval, the specific **Word Count Token-Frequency Penalty Formula**, and **Reciprocal Rank Fusion (RRF with $k=60$)** detailed in the architecture guide.
* **Security & IAM (IRSA Compliance):** Absolutely zero hardcoded AWS Access Keys or `.env` files with credentials. Production code relies entirely on standard AWS Credential Provider Chain. Kubernetes pods use IAM Roles for Service Accounts (IRSA) via WebIdentity token projection. Local code must let `boto3`/Go SDK resolve native AWS shared config profiles (`~/.aws/credentials`) transparently.
* **Kubernetes Memory Optimization Strategy:** All Python applications must adhere strictly to a **Lazy-Loading Pattern**. Framework components (e.g., Haystack `Pipeline`, `QdrantDocumentWriter`, `boto3`) must be imported and initialized dynamically only after a message is successfully pulled or when the application initializes its runtime components.

## 5. Terraform & Kubernetes Co-existence & IaC Architecture Rules
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

## 6. Current Phase & Engineering Tasks
* **[Task-01] Terraform: VPC Networking with PrivateLink Base**
  * Description: Provision private/public subnets and NAT Gateways. Configure AWS Bedrock VPC Interface Endpoints (AWS PrivateLink) inside the private subnet perimeter to eliminate internet egress.
* **[Task-02] Terraform: EKS Cluster Deployment & IAM IRSA Binding Profiles**
  * Description: Spin up managed EKS cluster with Spot-driven node groups. Generate AWS IAM Roles with precise OIDC trust relationships for S3 read, SQS process, and Bedrock InvokeModel actions.
