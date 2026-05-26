# 7: LLM Selection for Context Post-Processing and Generation

Date: 2026-05-26

## Status
Accepted

## Context
After retrieving and reranking the top-$K$ document chunks, the system must synthesize a final, coherent response for the user. This requires an LLM capable of:
1. Long-context comprehension (to ingest multiple retrieved chunks without truncation).
2. High adherence to system prompts (to mitigate hallucinations and strictly block answers not supported by the context).
3. Low cost per token, as this layer represents the primary variable operational expense of the RAG system.

## Decision
We adopt **Llama 3 (8B Instruct)** (or its latest cost-efficient iteration available via commodity API/Serverless hubs like AWS Bedrock or Anyscale) as the primary generation engine.

### Operational Constraints & Implementation Tactics:
1. **Off-Cluster Serverless Execution:** To protect the Kubernetes cluster from CPU/GPU starvation, we **strictly forbid** running the 8B model locally inside the EKS cluster during the MVP phase. Generation must be offloaded to serverless infrastructure (e.g., AWS Bedrock or an OpenAI-compatible serverless endpoint).
2. **Strict Context Pruning:** Before passing chunks to the LLM, the Go API must format the payload into a compact JSON string, stripping all non-essential metadata (e.g., internal database IDs, raw chunk hashes) to minimize token consumption and slash API billing.
3. **Rigid Guardrail Prompting:** The LLM system prompt must enforce a zero-tolerance policy for speculation: *«If the provided context does not contain the answer, reply with "I do not know". Do not use external knowledge.»*

## Consequences

### What becomes easier:
* **Cost Predictability:** Using a commodity 8B model via serverless APIs keeps the cost per 1K tokens negligible compared to frontier models (like GPT-4).
* **Cluster Resiliency:** The Go API acts as a simple HTTP client for the LLM, keeping the EKS cluster's CPU/RAM footprint lightweight and predictable.

### What becomes more difficult / Risks:
* **Vendor Dependency:** The system depends on the availability and latency of the upstream serverless LLM provider.
* **Reasoning Limits:** An 8B model has structural limitations in complex multi-step reasoning compared to larger models, which must be mitigated by superior data retrieval quality from Stages 1 & 2.
