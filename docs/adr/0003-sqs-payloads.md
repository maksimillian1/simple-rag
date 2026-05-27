# 3: Two-Stage SQS Payload Architecture for Document Chunks

Date: 2026-05-26

## Status

Accepted

## Context
During the ingestion pipeline of the `simple-rag` system, source documents uploaded to AWS S3 must be processed via a decoupled, two-stage asynchronous pipeline. Stage 1 (`apps/chunker`) downloads and parses documents into raw text chunks. Stage 2 (`apps/indexer`) extracts embeddings locally using an embedded `bge-small-en-v1.5` model (384-dimensions) and upserts them to Qdrant.

We need to formalize the architectural boundary and messaging contract between Stage 1 and Stage 2, specifically evaluating how chunked text is transferred.

Two options were considered for the Stage 1 $\rightarrow$ Stage 2 transition:
* **Option A (Split Storage / Claim Check Pattern):** Chunker writes parsed text chunk arrays to an intermediate, temporary Amazon S3 bucket and publishes only a lightweight pointer (S3 URI) to the SQS queue.
* **Option B (All-in-SQS Payload Pattern):** Chunker serializes raw text chunks and parent metadata directly into the JSON body of the Stage 2 SQS message, bypassing intermediate storage entirely.

## Architectural Assumptions & Constraints
1. **System Capacity:** Total target knowledge base size is up to 2 TB (Data-at-Rest). Petabyte scale is explicitly out of scope.
2. **Text-Only In-Flight Ingestion:** Stage 2 SQS messages contain **zero vector data**. Vector embedding calculations happen strictly on the consumer side inside the `apps/indexer` container layer.
3. **Atomic Message Boundary:** To prevent blast-radius contamination (where one corrupted file drops unrelated data into the DLQ), **one SQS message must contain chunks from exactly one source document**. Chunks from different files are never mixed inside a single message payload.
4. **Strict English Scope:** The system processes English language documents exclusively. Therefore, the character-to-byte ratio is deterministically 1 char = 1 byte, making payload size calculations computationally cheap.

## Architectural Decision
We select **Option B (All-in-SQS Payload Pattern)** using a two-queue architectural layout:
1. `stage-1-parsing` (Standard SQS): Receives native AWS S3 `ObjectCreated` event notifications.
2. `stage-2-indexing` (High-Throughput SQS): Receives atomic, single-file serialized text chunk envelopes produced by `apps/chunker`.

If a single document's text chunks aggregate to >245 KB, `apps/chunker` must programmatically split the chunks across multiple sequential SQS messages using a dynamic serialization size-guard loop.

## Cost Modeling & Economic Simulation (1 TB Baseline Load Test)

To prove financial viability, we model an ingestion stress-test of 1 TB of raw text documents.

### Simulation Baseline Metrics
* **Total Dataset Size:** 1 TB ($1,000,000,000$ KB).
* **Average Chunk Size:** 1,200 characters (~1.2 KB of clean English text $\approx$ 300 tokens).
* **Total Chunks Generated:** $\approx 833,333,333$ chunks.
* **Batching Density:** The payload size-guard packages chunks dynamically. Assuming an average of 150 chunks per document part to stay safely within the 245 KB envelope threshold:
  $$\text{Total Stage 2 Messages} = \frac{833,333,333 \text{ chunks}}{150 \text{ chunks/msg}} \approx 5,555,556 \text{ messages}$$
* **System Throughput:** Ingestion pipeline runs at a sustained rate of 2,000 chunks/sec via KEDA scaling. Total clearing time for 1 TB is $\approx 115.7$ hours.

### Option A: SQS + S3 (Split Storage)
* **Stage 1 SQS (S3 Events):** 5.55M messages $\times$ 3 actions (Write, Read, Delete) = 16.65M requests $\rightarrow$ **$6.66**
* **Intermediate S3 Storage:** 1 TB stored temporarily during the 115.7-hour run $\rightarrow$ **$3.54**
* **S3 API Requests (PUT by chunker, GET by indexer for 5.55M part files):** 11.1M requests $\rightarrow$ **$44.40**
* **Stage 2 SQS (Pointers):** 5.55M pointer messages $\times$ 3 actions = 16.65M requests $\rightarrow$ **$6.66**
* **Total Option A Cost:** **$61.26 per 1 TB processed**

### Option B: Two-Stage SQS Payload (All-in-SQS) - *ACCEPTED*
* **Stage 1 SQS (S3 Events - Minimalist Payload <64 KB):** 5.55M messages $\times$ 3 actions = 16.65M requests $\rightarrow$ **$6.66**
* **Stage 2 SQS (Payload Messages $\approx$ 180 KB each):** Each message is billed as 3 requests per action because AWS SQS charges 1 request per 64 KB block ($180 \text{ KB} / 64 \text{ KB} \approx 3$).
  $$\text{Total Billing Requests} = 5,555,556 \text{ messages} \times 3 \text{ actions} \times 3 \text{ blocks} = 50,000,004 \text{ requests}$$
  $$\text{Cost} = 50.00\text{M requests} \times \$0.40 / \text{M} \rightarrow \mathbf{\$20.00}$$
* **SQS Storage Premium Cost (Accumulated buffer queue volume during peak ingestion):** $\rightarrow$ **$4.10**
* **Total Option B Cost:** **$30.76 per 1 TB processed**

### Financial and Architectural Verdict
Option B is not only architecturally superior but **saves approximately 50% in cloud transaction fees** ($30.76 vs $61.26 per TB) at this scale. This economic inversion occurs because S3 API transaction costs ($0.005 per 1,000 PUTs) heavily penalize high-frequency object creation for small text-chunk files, far outweighing the SQS 64 KB payload billing premium.

Architecturally, Option B delivers:
1. **Strict Decoupling with Low Latency:** `apps/indexer` never communicates with S3, cutting down IAM surface visibility and eliminating network HTTP overhead on the synchronous ingestion path.
2. **Atomic Error Isolation:** If a message fails, only the chunks bound to that specific file are re-driven or moved to the DLQ.
3. **Zero Orphaned Infrastructure State:** SQS natively manages message expiration. There is zero risk of accumulating abandoned, un-deleted intermediate chunk files in S3.

## Consequences

### Pros
* **Superior FinOps Profile:** Eliminates costly S3 transaction overhead for high-frequency small-file writes.
* **Simplified IAM Security:** `apps/indexer` does not require read access to S3, enforcing the Principle of Least Privilege (PoLP).
* **Guaranteed Failure Domain:** Dead-lettering a message isolates a single document part without affecting the rest of the current pipeline state.

### Cons & Risks
* **SQS Outage Exposure:** The system depends heavily on SQS limits. Any unexpected downstream API changes or cluster-wide blocking of SQS access completely Halts pipeline progression.
* **Memory Headroom Caps:** Consumer jobs (`apps/indexer`) must fetch batches of messages (`MaxNumberOfMessages=10`), meaning up to 2.4 MB of raw text payload will be loaded into worker container memory simultaneously before triggering batch tensor inference. Pod memory resource limits must account for this headroom.
