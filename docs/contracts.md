# Data Contracts and Payload Specifications: simple-rag

This document establishes strict data contracts, wire formats, and payload validation schemas across the asynchronous ingestion boundaries and synchronous API layer. All components must strictly enforce these types.

---

## 1. Stage 1 Ingestion: S3 Object Created Event (Input)

AWS S3 triggers this payload to `stage-1-parsing` SQS queue. The worker must only care about the exact bucket name and object key.

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

**Enforced Constraint (FinOps / SQS Limit):** The absolute maximum size of an SQS message body is 256 KB. If a document spans hundreds of chunks, `apps/chunker` **MUST** split the sequence into multiple independent SQS messages.

To preserve ordering contexts, every message contains pagination metadata (`batch_index`, `total_batches`).
Every SQS message contains chunks from exactly one source document. If the document exceeds the token or byte threshold, it is partitioned across multiple messages.

### Wire Format (JSON Payload)
```json
{
  "trace_id": "18f98cda-5322-411a-96e0-2da650bf72f1",
  "document": {
    "file_id": "doc_9c2b4d5e",
    "file_name": "annual_report_2026.pdf",
    "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  },
  "boundaries": {
    "part_index": 0,
    "total_parts": 1
  },
  "chunks": [
    {
      "chunk_index": 0,
      "page_number": 1,
      "content": "Financial growth in Q1 exceeded target vectors by 14.2%. Operational costs remained flat due to spot fleet optimization."
    }
  ]
}
```

### Deterministic ID Rule for Indexer
To prevent vector duplication during AWS Spot evictions, `apps/indexer` must generate Qdrant Point IDs via `UUID5`:
```python
import uuid

# Namespace defined globally for the system
NAMESPACE_RAG = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')

def generate_point_id(file_id: str, chunk_index: int) -> str:
    # Deterministic string composite key
    composite_key = f"{file_id}:{chunk_index}"
    return str(uuid.uuid5(NAMESPACE_RAG, composite_key))
```

---

## 3. Synchronous Query Path Contracts (Go API)

### POST /api/v1/query (Request)
* Enforced Timeout: **4500ms**
* Payload Validation: Trim whitespace, minimum length 3 characters, maximum length 1000 characters.

```json
{
  "query": "What were the cost optimizations for infrastructure in Q1?",
  "top_k": 5,
  "alpha": 0.4
}
```
*Note: `alpha` controls the hybrid search balance between Dense (1.0) and Sparse (0.0) vector retrieval.*

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

Points in the Qdrant collection must incorporate dense vectors (384 dimensions), sparse matrices, and the following structured payload data layout:

```json
{
  "id": "a57608b4-b258-52b3-8fa9-dcd5dcd6c70b",
  "vector": {
    "dense": [0.0123, -0.4561, 0.7892, "... 384 floats total"],
    "sparse": {
      "indices": [102, 4056, 12904],
      "values": [0.45, 0.12, 0.88]
    }
  },
  "payload": {
    "file_id": "doc_9c2b4d5e",
    "file_name": "annual_report_2026.pdf",
    "chunk_index": 0,
    "page_number": 1,
    "text": "Financial growth in Q1 exceeded target vectors by 14.2%. Operational costs remained flat due to spot fleet optimization.",
    "indexed_at": 1779912000
  }
}
```
