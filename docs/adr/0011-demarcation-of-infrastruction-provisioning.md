# ADR-0011: Demarcation of Infrastructure Provisioning (Terraform) and Application GitOps (ArgoCD)

Date: 2026-06-22

## Status

Accepted

## Context

To implement the 4-Tier Compute Architecture defined in `ADR-0010`, we must establish a rigorous separation of concerns (Separation of Concerns) between core infrastructure provisioning and cluster-state configuration management. Managing every internal Kubernetes component via Terraform causes significant state drift, extends deployment lifecycles, and introduces catastrophic coupling between cloud networking resources and application-level software configurations.

Conversely, managing core cloud-native integration hooks (like network virtualization and node autoscaling) inside the cluster-level CD engine causes initialization deadlocks (e.g., deploying a Container Network Interface before the pods can bind IP addresses). We need a explicit "Line of Demarcation" to govern where automation artifacts are configured and executed, specifically accounting for Cilium's dual role as both the eBPF CNI fabric and the cluster's edge Kubernetes Gateway API controller.

## Decision

We enforce a strict technical boundary that splits cluster lifecycles into **Infrastructure Provisioning (Layer 1)** and **Declarative GitOps Configuration (Layer 2)**:

### 1. Layer 1: Infrastructure Foundations (Terraform)
Terraform is confined strictly to provisioning the physical/virtual cloud environment and bootstrapping EKS to an operational baseline. It utilizes the `helm_release` provider solely for core primitives that interface with the AWS API or are structurally required for cluster scheduling and global ingress/egress L4-L7 routing:
* **Cilium CNI & Gateway API Controller:** Essential for establishing eBPF-driven L4/L7 networking, native AWS VPC ENI routing, and private node communications. Cilium is explicitly configured with native Kubernetes Gateway API support enabled (`gatewayAPI.enabled=true`), acting as the primary Ingress fabric and terminating HTTP/gRPC traffic without external reverse-proxy daemons.
* **Karpenter Autoscaler:** Requires immediate execution to coordinate EC2 node creation. Terraform provisions the Karpenter controller onto an AWS Fargate Profile and instantiates its AWS-side infrastructure (SQS interruption queues, IAM Instance Profiles, and EventBridge intercept rules).
* **AWS EBS CSI Driver:** Required to map persistent cloud block storage (`gp3`) to stateful workloads inside the cluster boundary.
* **ArgoCD Controller Bootstrap:** Terraform executes a single installation of the ArgoCD Helm chart and registers the root Application manifest pointer (`deploy/k8s/environments/local`). After this execution, Terraform disengages from application lifecycle management.

### 2. Layer 2: Declarative GitOps Architecture (ArgoCD)
Every component that operates above the core networking, storage drivers, and compute scheduler layers is managed exclusively by ArgoCD using the **App-of-Apps pattern** located within the `deploy/k8s/` repository tree:
* **Platform Shared Services (`deploy/k8s/platform/`):** Cluster-wide operational software, including the KEDA scaling engine and core observability tooling.
* **L7 Traffic Routing Primitives:** Application-level `Gateway` and `HTTPRoute` Custom Resources matching the Cilium-backed Gateway API specification to expose the search endpoint.
* **Storage and Inference Primitives (`deploy/k8s/platform/qdrant`):** Deployment of the stateful Qdrant Vector DB, linking it to the Terraform-provisioned EBS storage classes.
* **Application Services (`deploy/k8s/apps/`):** End-user query layers (`apps/api`) and ephemeral batch runtimes (`apps/chunker`, `apps/indexer`).

```
[ Git Push to master ]
         │
         ▼
 ┌──────────────┐      Schedules      ┌────────────────────────────────┐
 │    ArgoCD    │────────────────────>│ KEDA, Qdrant, Go API, Workers  │
 └──────────────┘                     └────────────────────────────────┘
         ▲                                             │
         │ Reconciles State                            │ Binds to Network
         │                                             ▼
 ┌──────────────┐                      ┌───────────────────────────────┐
 │  Terraform   │────────────────────> │ EKS, Cilium (CNI+Gateway API) │
 └──────────────┘Provisions Primitives │ Karpenter, AWS EBS CSI Driver │
                                       └───────────────────────────────┘
```

## Consequences

* **Mitigation of State Drift:** Application parameters, resource quotas, and image tag tracking configurations are modified without evaluating the monolithic cloud-provider infrastructure state.
* **Deadlock Prevention:** Deploying Karpenter and Cilium via Terraform guarantees that when ArgoCD initializes, the networking layer is functional, the Gateway API CRDs are registered, and the node provisioner can instantly scale resources to accommodate incoming platform pods.
* **Streamlined Disaster Recovery:** Total cluster restoration can be executed in two steps: a single `terraform apply` sequence to generate the computing fabric and inject the ArgoCD root application, followed by automatic ArgoCD synchronization to reconstruct all database and pipeline states.
* **Clean Open-Source Extension:** External developers can completely evaluate, audit, and patch the platform architecture (`deploy/k8s/`) without requiring execution tokens or code validation privileges inside the private AWS cloud account.
