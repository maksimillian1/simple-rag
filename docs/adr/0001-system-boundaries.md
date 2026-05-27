# ADR-0001: System Boundaries & Core Components

Date: 2026-05-27

## Status

Accepted

## Context

Our RAG (Retrieval-Augmented Generation) pipeline requires a strict separation of concerns between heavy, non-deterministic document processing and low-latency user querying. To leverage cost-efficient AWS Spot Instances without risking state corruption or data loss, the ingestion pipeline must be decoupled into independent, stateless, event-driven phases.

We have designed a Two-Stage Asynchronous Ingestion Pipeline where both processing phases are built on top of the Haystack 2.0 framework and executed as ephemeral, short-lived Kubernetes Jobs managed by KEDA.

The updated interaction and boundaries map is shown in the official [Architecture Diagram](../architecture.md#data-flow-diagram).

## Decision

We establish the following strict system boundaries, architectural rules, and data constraints:

1. **Data Ingestion Entry Point & PoC Scope Guardrails (S3):** AWS S3 acts as the decoupled, immutable entry point for raw documents. For the current PoC/Demo perimeter, the system operates under a **Trusted Ingress Assumption** where files are uploaded directly to the bucket (`prod-raw-documents-eu-west-1`) via secure admin channels (AWS Console or AWS CLI).
   * **PoC Boundary Definition:** Upstream user-facing API gateways, CORS configurations, and cryptographic Presigned POST size-enforcements (`content-length-range`) are explicitly out of scope for this isolated ingestion phase.
   * **Compute-Layer Fail-Safe:** To protect downstream Kubernetes node resources from memory exhaustion (OOM), a strict **Max File Size Limit of 100 MB** is enforced inside the Stage 1 Chunker Job. The worker parses the incoming SQS metadata *before* downloading the object. If `Records[0].s3.object.size > 104857600 bytes` (100 MB), the worker removed such item from a queue, logs a structured alert, and continue if possible.

2. **Stage 1 Processing Boundary (Haystack Chunker):** Driven by KEDA `ScaledJob` tied to the `stage-1-parsing` SQS queue. This job downloads the raw file from S3, executes heavy parsing/text extraction via the Strategy Pattern, and slices it into semantic chunks using Haystack components.
   * **Data Contract Transition:** Instead of writing intermediate chunks back to S3 (which introduces expensive S3 API transaction costs), Stage 1 packs the array of text chunks and metadata directly into the JSON payload of the next queue (`stage-2-indexing`), keeping it strictly under the 256 KB SQS limit.

3. **Stage 2 Processing Boundary (Haystack Indexer):** Driven by KEDA `ScaledJob` tied to the `stage-2-indexing` SQS queue. This job takes the pre-calculated chunks directly from the SQS message body, executes embedding generation locally utilizing an **embedded `bge-small-en-v1.5` model** baked directly into the image layer, and performs a deterministic gRPC upsert into Qdrant VectorDB.

4. **Query Boundary:** A lightweight, synchronous, always-on Go API service (`apps/api`). It operates exclusively on the read path, executing hybrid vector queries against Qdrant, performing Reciprocal Rank Fusion (RRF), and interacting with a serverless LLM provider for low-latency context synthesis.

5. **Network & Resource Isolation:** All components are deployed within an isolated Kubernetes Namespace. Cross-component traffic is tightly restricted at L4/L7 via Cilium Network Policies:
   * `chunker` Job can only initiate connections to external AWS S3 and AWS SQS.
   * `indexer` Job can only initiate connections to AWS SQS and the Qdrant gRPC endpoint.
   * `Go API` has inbound access from users, outbound gRPC access to Qdrant, and HTTPS outbound access to the serverless LLM gateway. Direct access from the Go API to SQS or S3 is blocked.

## Consequences

* **Controlled Spot Resilience:** Since both processing phases run as native Kubernetes Jobs under a strict "Zero-Daemon" policy, the system is highly resilient to sudden AWS Spot evictions. Jobs trap the 2-minute AWS `SIGTERM` warning to gracefully flush active operations. If a node drops abruptly mid-execution, the active SQS message naturally reappears in the queue after the Visibility Timeout expires and is re-processed.
* **Zero Idle Compute Costs:** When there are no documents to process, both SQS queues are empty, and KEDA scales the number of running Chunker and Indexer jobs to absolute zero, eliminating idle cluster costs.
* **FinOps S3 Optimization:** Bypassing S3 for intermediate chunk storage completely eliminates S3 PUT/GET API request charges on large-scale document parsing operations.
* **Payload Constraints:** The Haystack Chunker (Stage 1) must guarantee that any batch of chunks sent to `stage-2-indexing` fits within the 256 KB SQS payload threshold. If a document yields a larger structure, the job must split the output across multiple chunk arrays and send them as separate SQS messages.
* **Database Idempotency Requirement:** Stage 2 (Indexer) MUST use deterministic point IDs for vector upserts via `UUID5(file_name + chunk_index)`. This ensures that if an AWS Spot instance drops during the final database write, the retried job will overwrite the existing vectors rather than duplicating them in Qdrant.
* **Eventually Consistent Ingest:** Document availability for RAG querying is eventually consistent and depends on the total transit time through both SQS processing blocks.
* **Anomalous File Observability:** Rejected files exceeding the 100 MB threshold or causing ingestion failures are automatically tracked via log-routing pipelines. Dead-Letter Queues (DLQ) are established for both `stage-1-parsing-dlq` and `stage-2-indexing-dlq` to isolate toxic payloads without interrupting operational pipeline metrics.
