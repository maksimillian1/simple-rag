# ADR-0008: Terraform Local Test Mode & Module Isolation

Date: 2026-06-17

## Status

Accepted

## Context

Our RAG infrastructure requires AWS resources to run in staging and production. During local development and testing, developers run the application services locally but still need to target real AWS S3 and SQS resources (AWS Native ingestion) for end-to-end integration testing. However, heavy network topology resources (VPC, NAT instance, PrivateLink) are not required and should not be provisioned locally.

Initially, we implemented a root-level condition `count = var.is_local_test ? 0 : 1` on the `rag_storage` module call itself. While this successfully prevented remote resource creation, it completely disabled S3 and SQS as well, and forced all root-level outputs to use list indexes.

## Decision

We establish the following architectural guidelines for handling local test mode in Terraform:

1. **Always-Instantiated Module**: The `rag_storage` module must always be instantiated by the root module, regardless of the environment.
2. **Selective Resource Conditionalization**: The `is_local_test` boolean flag is passed into the module to selectively disable heavy network resources:
   * **VPC, VPC Endpoints, and NAT instance** calls enforce `count = var.is_local_test ? 0 : 1`.
   * **S3 Bucket, SQS Queues, DLQs, Policies, and Notifications** are always provisioned (`count` is omitted) so they are available for local testing.
3. **Safe Output Handling**: The module's `outputs.tf` will return direct attributes for S3 and SQS, and will use the `one(...)` function to safely return either the resource attribute or `null` for the conditional VPC resources.
4. **Simplified Root Interface**: The root outputs query the module attributes directly (e.g., `module.rag_storage.s3_bucket_name`) without module-level array indexing.

## Consequences

* **Clean Root Topology**: The root `main.tf` has a standard interface without conditional lists.
* **Self-Contained Module Logic**: The choice of whether to provision heavy network infrastructure is encapsulated inside the `rag_storage` module.
* **Ingestion Readiness**: Developers running local integration testing have access to the necessary S3 bucket and SQS queues natively, while avoiding the cost and complexity of a private VPC perimeter.
