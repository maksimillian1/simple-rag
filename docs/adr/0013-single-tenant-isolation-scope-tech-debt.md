# ADR-0013: Single-Tenant Scope Isolation and Multi-Tenancy Technical Debt Definition

## Status
Proposed

## Context
The system was initially conceptualized with multi-tenancy requirements to allow parallel, isolated RAG pipelines within a single Kubernetes cluster. However, providing dynamic multi-tenancy at the initial deployment stage introduces structural complexity across the infrastructure and configuration planes, significantly increasing the validation and testing overhead required for the `v1.0.0` release.

To prevent architectural drift and maintain a clear ledger of technical debt, the specific engineering boundaries that limit immediate multi-tenancy deployment must be formalized across all system layers.

## Decision
We reject the immediate implementation of dynamic multi-tenant infrastructure. The initial production release (`v1.0.0`) will strictly enforce a **Single-Tenant Architecture** running inside a deterministic, statically provisioned infrastructure scope.

The multi-tenancy roadmap is officially deferred to future releases, bound by the following friction points and architectural bottlenecks identified in the current layout:

### 1. GitOps Orchestration Layer (ArgoCD & Image Updater)
* **Current Boundary:** The flat directory topology (`deploy/k8s/apps/*`) combined with a loose `git` generator forces a single-instantiation model per cluster directory.
* **Required Upgrade:** Transitioning to a Kustomize `base/overlays` directory structure. The `ApplicationSet` must switch from a simple `git` directory generator to a strict `list` generator (explicitly defining tenant variables) or a complex `git` matrix generator. Additionally, `ArgoCD Image Updater` annotations must be refactored to handle comma-separated multi-image lists within a single aggregated tenant application manifest, increasing configuration fragility.

### 2. Identity Security and Kubernetes Operators (AWS IAM)
* **Current Boundary:** EKS Pod Identity associations are hardcoded to static namespaces, ensuring tight security boundaries but zero runtime flexibility.
* **Required Upgrade:** Choosing between two high-coupling architectural tradeoffs:
    * *Option A:* Leveraging traditional IRSA (IAM Roles for Service Accounts) with loose wildcard condition masks (`system:serviceaccount:rag-tenant-*:*`). This introduces severe security vulnerabilities and violates the Least Privilege principle.
    * *Option B:* Introducing third-party cluster operators like AWS Controllers for Kubernetes (ACK) or Crossplane. This eliminates IAM wildcard coupling by declaring `PodIdentityAssociation` as CRDs inside GitOps, but introduces heavy operational overhead, CRD lifecycle maintenance, and increased cluster bootstrap latency.

### 3. Infrastructure Module Decoupling (Terraform `02-rag-k8s`)
* **Current Boundary:** The `02-rag-k8s` module acts as a rigid, flat-line provisioning block that expects a single backend state and single target variables for cluster objects.
* **Required Upgrade:** The module signature must be completely refactored to accept complex variables (e.g., `list(string)` or `map(object)` containing unique tenant identifiers). Terraform logic must implement native `for_each` loops across all IAM, S3, SQS, and `aws_eks_pod_identity_association` resource declarations to dynamically generate infrastructure for each declared tenant. This increases structural coupling, as adding a new tenant requires an explicit Terraform state mutation.

### 4. Cross-Plane Architectural Coupling (Terraform + ArgoCD Deadlock)
* **Current Boundary:** There is an implicit synchronous dependency between infrastructure provisioning (Terraform creating SQS queues/IAM roles) and deployment state enforcement (ArgoCD creating workloads).
* **Required Upgrade:** True SaaS multi-tenancy demands that spinning up a new tenant requires *zero* Terraform execution. Achieving this requires moving all cloud resource definitions out of native Terraform and shifting to a cloud-control infrastructure loop inside Kubernetes (e.g., ACK or Crossplane managing SQS/S3 dynamically via GitOps manifests). This alters the platform's foundational Layer 1 vs Layer 2 demarcation line.

### 5. Shared In-Cluster Compute Resources (The Noisy Neighbor Problem)
* **Current Boundary:** The shared TEI (Text Embeddings Inference) service runs as a unified deployment scaled by KEDA based on a global queue metric.
* **Required Upgrade:** Under multi-tenancy, a single tenant flooding the system with documents could completely deplete TEI compute capacity or consume all Qdrant vector storage IOPS. Mitigating this requires introducing advanced Kubernetes `ResourceQuotas`, `LimitRanges`, and dedicated Karpenter node taints per tenant, which drastically drives up overall AWS infrastructure running costs.

## Consequences
* **Positive:** Guaranteed validation and deployment of the `v1.0.0` release within a predictable timeframe. Zero dependency on experimental or resource-heavy cluster operators. Bulletproof security posture satisfying standard single-tenant compliance out of the box.
* **Negative:** Deploying a parallel isolated RAG pipeline currently requires duplicating the GitOps folder structure or spinning up an entirely separate EKS cluster instance.
* **Mitigation:** Application code (Go API, Python Workers) must remain completely stateless, environment-agnostic, and independent of hardcoded namespace strings to guarantee that migrating to the future multi-tenant model remains a pure configuration and infrastructure-plane change without code refactoring.
