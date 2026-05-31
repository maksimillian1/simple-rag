# Operations and Day-2 Infrastructure Manual: simple-rag

This document defines the operational runbooks, FinOps verification metrics, emergency recovery paths, and scaling configurations for running the `simple-rag` pipeline on production AWS Spot infrastructure.

---

## 1. Spot Eviction Handling & Graceful Shutdown

Compute workloads for `apps/chunker` and `apps/indexer` execute on cost-optimized AWS Spot Instances. When AWS reclaims an instance, the node receives a strict 2-minute notice via the EC2 metadata endpoint.

### Graceful Termination Mechanism
The cluster infrastructure architecture relies on `aws-node-termination-handler` to intercept the eviction event, taint the node, and broadcast a standard `SIGTERM` signal to all active pods.
* **Signal Interception:** Upon trapping `SIGTERM`, the internal execution loop of the worker process must immediately halt SQS long-polling operations.
* **Inflight Ingestion Flush:** The container is granted a 120-second grace window to complete processing the current active payload batch, execute deterministic gRPC upserts to Qdrant, delete the completed message from SQS, and issue a clean `exit 0`.
* **Idempotency Guarantee:** If a hard eviction kills the pod before the active batch is deleted from SQS, the message visible visibility timeout expires, and another worker picks it up. Data duplication inside Qdrant is blocked atomically via deterministic `UUID5(file_name + chunk_index)` point ID generation, converting retries into safe overwrites.

---

## 2. KEDA Autoscaling Architecture

To prevent cluster thrashing and minimize resource utilization overhead, horizontal auto-scaling is managed strictly via Kubernetes **`ScaledJob`** resources instead of standard `ScaledObject` deployments.

### Dynamic Provisioning Metrics
* **Queue-Driven Scaling:** The KEDA controller monitors the SQS queue lengths via high-frequency API polling intervals.
* **Job Allocation Target:** The scaler instantiates parallel dedicated Kubernetes `Job` objects based on a target ratio of **1 parallel job per 10 messages** pending in the queue, up to a strict infrastructure quota limit (`maxReplicaCount = 20`).
* **Natural Scale-In:** Resource contraction happens natively from within the application layer. When a worker process receives an empty response from the SQS long-poll request, it automatically breaks its processing loop and terminates cleanly (`exit 0`). Kubernetes automatically garbage-collects completed job pods, scaling compute resource consumption back to absolute zero when idle.

---

## 3. Ingestion Assumptions & Scope Boundaries

For the current Alpha deployment, the ingestion pipeline operates under a **Trusted Ingress Assumption** to reduce API gateway validation overhead during testing.

### Operational Guardrails
1. **Trusted Ingress Perimeter:** Source files are dropped directly into the designated S3 raw bucket via authorized enterprise channels (AWS CLI/Console utilizing local profiles). Files are assumed to be structurally sound before landing.
2. **Compute-Layer Memory Protection:** Despite ingress assumptions, the `chunker` application enforces localized memory boundary protection. The process parses the S3 object metadata length parameter directly from the SQS payload *before* initiating network download streams. If the file size exceeds a hard limit of **100 MB**, the download path is aborted, a structured alert is logged, and the payload is shunted to protect pod RAM allocations.
3. **Production Transition Blueprint:** Transitioning to full production environments requires decoupling ingestion by implementing an upstream API/Gateway layer. This gateway must enforce tight `Content-Length` validation and multi-part structural linting *before* generating AWS S3 Presigned URLs, isolating heavy validation processing outside the asynchronous ingestion boundary.

---

## 4. FinOps & Cost-Efficiency Verification

To prove the financial ROI of the zero-daemon ephemeral architecture to business stakeholders, infrastructure teams must track the **Cost-Per-Document-Indexed (CPDI)** metric.

### CloudWatch Log Insights Query
Infrastructure engineers can audit the efficiency of the self-terminating loop and calculate exact compute execution runtimes using this analytical query:
```sql
fields @timestamp, @message
| filter @message like /Terminating ephemeral job process/ or @message like /Worker activated/
| sort @timestamp desc
```

### Business KPI Dashboard Formula
The total cost efficiency of the RAG pipeline incorporates serverless API invocations, storage transactions, and spot compute durations:

$$\text{CPDI} = \frac{\text{Amortized S3/SQS API Costs} + (\text{Spot Node Compute Duration} \times \text{Spot Rate}) + (\text{AWS Bedrock Input/Output Token Count} \times \text{Token Rate})}{\text{Total Successfully Upserted Vector Points}}$$

### Target Financial ROI Metrics
* **Idle State Cost:** **$0.00** across all ingestion layers (`chunker`, `indexer`, and embedding generation components) when queues are empty.
* **Active Processing Ceiling:** **<$0.02** per standard 100-page corporate PDF document (including vectorization via colocated TEI sidecar and response generation via serverless AWS Bedrock Llama 3 8B).

---

## 5. Troubleshooting & Dead-Letter Queue (DLQ) Runbook

Malformed document structures, unsupported binary payloads, or network blocks that cause successive processing crashes are safely isolated via an automated SQS Redrive Policy.

### Disaster Recovery Step-by-Step

1. **Isolate Toxic Payloads:**
   When a message fails processing **3 times** consecutively, the primary SQS queue automatically shunts the payload to its sibling dead-letter queue (`-dlq`). Audit the payload structure using the AWS CLI:
   ```bash
   aws sqs receive-message --queue-url [https://sqs.eu-west-1.amazonaws.com/](https://sqs.eu-west-1.amazonaws.com/)<aws_account_id>/stage-2-indexing-dlq --max-number-of-messages 1
   ```
2. **Verify Integrity State:**
   Extract the `file_id` or unique metadata properties from the isolated payload. Query the Qdrant Vector DB instance cluster from inside the private VPC subnet to identify if partial data fragments exist:
   ```bash
   curl -X POST [http://qdrant.simple-rag.svc.cluster.local:6333/collections/demo_collection/points/recommend](http://qdrant.simple-rag.svc.cluster.local:6333/collections/demo_collection/points/recommend) \
     -H "Content-Type: application/json" \
     -d '{"filter": {"must": [{"key": "file_id", "match": {"value": "TARGET_FILE_ID"}}]}}'
   ```
3. **Patch and Redrive Protocol:**
   * Investigate structured application logs to identify if the failure stemmed from a parsing layout error in `apps/chunker` or a configuration mismatch.
   * Apply code updates, rebuild the container images, and allow the GitOps pipeline to update cluster state.
   * Execute the native AWS CLI SQS message redrive tool to shift packets back from the DLQ into the active ingestion stream without data loss.
