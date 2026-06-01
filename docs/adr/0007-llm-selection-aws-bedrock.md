# 7: AWS Bedrock (Llama 3.2 3B Instruct) Selection for Context Generation

Date: 2026-05-31

## Status
Accepted (Supersedes previous generic serverless definition)

## Context
After retrieving and reranking the top-$K$ document chunks via dual-stage hybrid retrieval and Reciprocal Rank Fusion ($k=60$), the system must synthesize a final response. This requires an LLM capable of long-context comprehension, high system prompt adherence to block hallucinations, and minimal operational cost.

While generic commodity APIs (OpenAI, DeepSeek) provide similar token structures, they introduce corporate compliance risks, public internet egress costs, and overhead from long-lived API key management (Secrets Rotation).

## Decision
We explicitly adopt **AWS Bedrock running Meta Llama 3.2 (3B Instruct)** as the primary generative engine.

### Operational Constraints & Implementation Tactics:
1. **IAM IRSA Native Authentication:** We strictly ban the injection of long-lived API keys (`LLM_API_KEY`) into the EKS cluster runtime. The Go API (`apps/api`) will utilize the official `aws-sdk-go-v2/service/bedrockruntime` client. Authentication is delegated to the EKS OIDC provider via standard Kubernetes ServiceAccount annotations (`eks.amazonaws.com/role-arn`), invoking the role mapped to the `bedrock:InvokeModel` policy.
2. **Zero-Internet Network Egress (FinOps & SecOps):** In the production environment, requests from the Go API to AWS Bedrock must flow entirely through an **AWS Bedrock VPC Endpoint (AWS PrivateLink)**. This enforces an absolute data privacy boundary (the text chunks never touch the public internet) and slashes NAT Gateway data processing charges.
3. **Rigid Guardrail Prompting:** The prompt format must comply with the Llama 3 Instruct special token standard (`<|begin_of_text|>`, `<|start_header_id|>system<|end_header_id|>`) to enforce deterministic instruction compliance.

## Consequences

### What becomes easier:
* **Security & Compliance:** Zero API keys to rotate. Enterprise-grade trust isolation where customer documents remain strictly within the VPC perimeter.
* **Cost Efficiency:** On-Demand serverless pricing charges exclusively per input/output token processed ($Pay-per-token$), scaling operational spend down to absolute zero when the system is idle.

### What becomes more difficult / Risks:
* **AWS Vendor Lock-In:** The query layer code shifts from standard OpenAI HTTP clients to the specialized AWS Bedrock SDK model payload wrappers. This is mitigated by isolating Bedrock logic behind a clean Go `LLMProvider` interface.
