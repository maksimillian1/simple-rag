# Data Contracts and Payload Specifications: simple-rag

This document establishes strict data contracts, wire formats, and payload validation schemas across the asynchronous ingestion boundaries and synchronous API layer. All components must strictly enforce these types.

---

## 1. Stage 1 Ingestion: S3 Object Created Event (Input)

AWS S3 triggers this payload to `stage-1-parsing` SQS queue. The worker component evaluates only the exact bucket name, object key, and object size.

### JSON Schema
```json
{
  "$schema": "[http://json-schema.org/draft-07/schema#](http://json-schema.org/draft-07/schema#)",
  "title": "S3EventNotification",
  "type": "object",
  "required": ["Records"],
  "properties": {
    "Records": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["s3"],
        "properties": {
          "s3": {
            "type": "object",
            "required": ["bucket", "object"],
            "properties": {
              "bucket": {
                "type": "object",
                "required": ["name"],
                "properties": {
                  "name": { "type": "string" }
                }
              },
              "object": {
                "type": "object",
                "required": ["key", "size"],
                "properties": {
                  "key": { "type": "string" },
                  "size": { "type": "integer", "minimum": 1 }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

---

## 2. Stage 2 Inter-Queue Payload: Document Chunks

**CRITICAL INFRASTRUCTURE GUARDRAILS (FinOps & SQS Limits):**
1. **SQS Hard Limit Mitigation:** The absolute maximum size of an SQS message body is 256 KB. If a document yields chunks aggregating to >245 KB (safety headroom), `apps/chunker` MUST split the sequence across multiple independent SQS messages.
2. **Atomic Message Boundary:** Every SQS message contains chunks from exactly *one* source document. A single document can be sliced into multiple messages (parts), but a single message *never* mixes chunks from different documents.

### INDEX DISTINCTION & IDEMPOTENCY CONTRACT (READ BEFORE IMPLEMENTATION):
* **`boundaries.part_index` (Message Level):** Tracks the index of the SQS message container itself for a partitioned file. Used solely for progress tracking and log metrics. **NEVER** use this to generate vector database IDs.
* **`chunks[].chunk_index` (Data Layer Level):** MUST be a strictly monotonic, global, progressive index across the entire file. If a file is split into multiple SQS messages, **`chunk_index` DOES NOT reset to 0 in the subsequent messages.** It continues sequentially. This ensures deterministic idempotency and prevents vector data truncation (overwriting).

### Wire Format (JSON Payload)
```json
{
  "trace_id": "18f98cda-5322-411a-96e0-2da650bf72f1",
  "document": {
    "file_id": "doc_9c2b4d5e",
    "file_name": "annual_report_2026.pdf"
  },
  "boundaries": {
    "part_index": 0,    // Message sequence number (0, 1, 2...). Resets per file.
    "total_parts": 2    // Total SQS messages emitted for this single large file.
  },
  "chunks": [
    {
      "chunk_index": 0, // Global absolute position inside annual_report_2026.pdf
      "page_number": 1,
      "content": "Financial growth in Q1 exceeded target vectors by 14.2%. Operational costs remained flat due to spot fleet optimization."
    },
    {
      "chunk_index": 1, // Global increment continues
      "page_number": 1,
      "content": "Second chunk text layer goes here..."
    }
  ]
}
```

### Deterministic ID Rule for Indexer
To guarantee absolute resiliency against AWS Spot Instance evictions, `apps/indexer` calculates Qdrant Point IDs via `UUID5`.

Because `chunk_index` is globally unique and continuous across the entire document lifetime, a crashed-and-retried ingestion batch will atomically overwrite existing vectors instead of duplicating them or wiping out unrelated parts.

```python
import uuid

# Immutable Namespace defined globally for the simple-rag architecture
NAMESPACE_RAG = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')

def generate_point_id(file_name: str, global_chunk_index: int) -> str:
    """
    Generates a deterministic UUID5 point ID for Qdrant.
    
    WARNING: global_chunk_index must be the absolute sequential index from the 
    beginning of the file, NOT an internal array index within a single SQS message.
    """
    # Composite key relies strictly on immutable file name and absolute index
    composite_key = f"{file_name}:{global_chunk_index}"
    return str(uuid.uuid5(NAMESPACE_RAG, composite_key))
```

---

## 3. Synchronous Query Path Contracts (Go API)

### POST /api/v1/query (Request)
* Enforced Gateway Timeout: **4500ms**
* Payload Validation: Trim whitespace, minimum length 3 characters, maximum length 1000 characters.

```json
{
  "query": "What were the cost optimizations for infrastructure in Q1?",
  "top_k": 5,
  "alpha": 0.4
}
```
*Note: `alpha` controls the hybrid search balance between Dense (1.0) and Sparse (0.0) vector retrieval inside Qdrant.*

### POST /api/v1/query (Response)
Returns the generated text from Llama 3 along with explicit citations and confidence metadata mapped from Qdrant vectors.

```json
{
  "answer": "Infrastructure costs in Q1 were reduced through the deployment of an ephemeral spot fleet and event-driven architectures.",
  "execution_time_ms": 342,
  "citations": [
    {
      "document_id": "doc_9c2b4d5e",
      "file_name": "annual_report_2026.pdf",
      "page_number": 1,
      "score": 0.892,
      "text_snippet": "Operational costs remained flat due to spot fleet optimization."
    }
  ]
}
```

---

## 4. Vector Storage Schema (Qdrant Point Payload)

Points in the Qdrant collection incorporate dense vectors generated via the shared TEI Service, sparse vector tokens generated in-app by the indexer worker, and structured context metadata.

```json
{
  "id": "a57608b4-b258-52b3-8fa9-dcd5dcd6c70b", // Generated via UUID5(file_name + chunk_index)
  "vector": {
    "dense": [0.0123, -0.4561, 0.7892, "... 384 floats total from TEI"],
    "sparse": {
      "indices": [102, 4056, 12904], // Term token indices calculated by indexer
      "values": [0.45, 0.12, 0.88]     // TF-IDF / BM25 token weights
    }
  },
  "payload": {
    "file_id": "doc_9c2b4d5e",
    "file_name": "annual_report_2026.pdf",
    "chunk_index": 0,                  // Preserved absolute global chunk index
    "page_number": 1,
    "text": "Financial growth in Q1 exceeded target vectors by 14.2%. Operational costs remained flat due to spot fleet optimization.",
    "indexed_at": 1779912000            // Epoch timestamp of ingestion completion
  }
}
```
