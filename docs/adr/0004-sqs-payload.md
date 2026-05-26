# 4. Using SQS Payload to Transfer Document Chunks

Date: 2026-05-25

## Status

Accepted

## Context
During the ingest stage of the RAG system, source documents are parsed into text chunks (Stage 1), which must then be safely passed to the next stage for vectorization and indexing (Stage 2). We need to select an efficient intermediate storage and messaging solution between these stages.

Two primary options were considered:

Option A (Split Storage): Write chunk batches to an intermediate Amazon S3 bucket and pass only the object references (S3 URIs) via Amazon SQS.

Option B (All-in-SQS): Batch the parsed chunks directly inside the JSON body (Payload) of SQS messages.

## Architectural Assumptions
1. **System Capacity:** This RAG system is designed to work with a knowledge base of up to 2 TB (Data-at-Rest). The project does not envisage petabyte scale.
2. **Queue Throughput:** Queue unloading speed (Stage 2) based on TEI + Qdrant workers is several times faster than the network download speed of source files (Network Ingress).
3. **Data lifetime in the queue:** The queue is strictly ephemeral. Based on points 1 and 2, any peak batch load is guaranteed to be cleared by the system in less than 24 hours. The queue will never accumulate gigabytes of data in long-term storage mode.

## Solution
We select Option B (SQS Payload). Parsed document chunks will be aggregated into arrays and sent directly within the JSON body of SQS messages.

To maximize throughput efficiency and minimize Amazon SQS API call costs, chunks will be packed into batches of up to 40 chunks per message (~240 KB), ensuring they stay safely under the strict Amazon SQS 256 KB maximum payload limit.

## Cost Modeling (for 1 TB Load Test)

To validate this decision against potential cloud spend, an economic simulation was conducted for a baseline 1 TB ingestion test. The workload runs against a fixed compute pool (e.g., a Kubernetes cluster node pool limited to 8 CPU / 8 GB RAM, processing at a sustained rate of ~2,000 chunks/sec).

### Baseline Metrics
* **Total Ingest Volume:** 1 TB (~1,000,000,000 KB).
* **Chunk Size:** ~6 KB (1536-dim embedding vector `float32` + metadata).
* **Total Chunks:** ~166,666,667.
* **Test Duration:** ~23.1 hours to clear 1 TB at 2,000 chunks/sec.

### Option A: SQS + S3 (Split Storage)
*Assumptions: Mixed file sizes with an average of 250 chunks (1.5 MB) per S3 file due to various source document sizes (60% large files up to 1000 chunks, 40% small files). Data is temporarily duplicated in a standard bucket (x2 storage factor).*

* **SQS Requests:** ~2M lightweight pointer requests $\rightarrow$ **$0.80**
* **S3 Requests (PUT/GET for 666,667 files):** $\rightarrow$ **$3.60**
* **S3 Storage Cost (1 TB avg over 23.1h with x2 factor):** $\rightarrow$ **$0.73**
* **Total Option A Cost:** **~$5.13 per 1 TB**

### Option B: SQS Payload (All-in-SQS) - *ACCEPTED*
*Assumptions: Chunks are batched directly into the SQS message body up to 40 chunks per message (~240 KB out of the 256 KB limit) to minimize API calls. SQS bills every 64 KB of payload as 1 request.*

* **SQS Requests:** ~4.16M messages. Due to the 240 KB payload size, each message counts as 4 requests. Totaling ~33.7M billing requests (Write + Read + Delete) $\rightarrow$ **$13.49**
* **SQS Storage Cost (500 GB average volume over 23.1h at $0.40/GB-month):** $\rightarrow$ **$6.33**
* **Total Option B Cost:** **~$19.82 per 1 TB**

### Financial and Architectural Verdict
While **Option B (SQS Payload)** is approximately **4x more expensive** in terms of cloud infrastructure for mass data dumps ($19.82 vs $5.13 per TB), the absolute financial delta (~$15 per 1 TB) is **negligible** for a typical Enterprise RAG workload where massive ingestions are rare events.

The **Option B** is chosen because it significantly reduces engineering complexity:
1. **No Cold-Start / I/O Overhead:** Eliminates S3 network hops during Stage 2.
2. **Simplified State Management:** No need to manage temporary S3 buckets, object lifecycles, or edge cases where SQS messages succeed but S3 object deletion fails (orphan files).
3. **Infrastructure Simplicity:** Single point of failure (SQS) instead of two coupled services (SQS + S3).

## Consequences

Pros
* Lower Engineering Complexity: Drastically reduces development time and time-to-market. There is no need to write, maintain, and test code for managing temporary S3 bucket lifecycles or handling multi-part uploads for small files.
* No I/O or Network Overhead: Eliminates an intermediate network hop (Stage 1 -> S3 -> SQS -> Stage 2 becomes a clean Stage 1 -> SQS -> Stage 2). Stage 2 workers immediately access data without making additional S3:GetObject API calls.
* Improved System Reliability: Avoids complex edge-case handling, such as "orphan files" in S3 that occur when an SQS message fails or gets deleted, but the corresponding S3 object deletion fails. SQS natively guarantees message cleanup via its lifecycle.

Cons & Risks
* SQS Storage Pricing Sensitivity: If a critical downstream system failure occurs at Stage 2 and the processing workers go down for an extended period during a massive data dump, storing large volumes of messages in SQS will scale up costs ($0.40–$0.50 per GB-month).

Mitigation
* Infrastructure Monitoring: Configure a dedicated alert in Prometheus/CloudWatch that triggers if the total volume of visible messages in the SQS queue exceeds 500 MB, signaling worker degradation or downtime.
* Backlog Protection: Maintain a strictly defined MessageRetentionPeriod (e.g., 4 days) and leverage a Dead Letter Queue (DLQ) to automatically isolate unprocessable or stalled messages without blowing up primary queue storage costs.
