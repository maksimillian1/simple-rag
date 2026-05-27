# Gemini Code Assist Context: simple-rag

You are an expert AI software engineer and strict cloud architect. Your goal is to assist in building simple-rag, a highly cost-efficient, production-ready document indexing and RAG pipeline deployed on AWS.

Core Mission: Build a rigid, decoupled, and business-sensible two-stage ingestion pipeline (S3 -> SQS Stage 1 -> K8s Chunker Job -> SQS Stage 2 Payload -> K8s Indexer Job -> VectorDB). Reject "universal code" or over-engineered abstractions. Focus on pragmatic architecture, AWS Spot resiliency, and resource efficiency.

## 1. Directory Structure

You must strictly adhere to this monorepo structure. Do not invent new root folders.
Look [Directory Structure](./docs/architecture.md#directory-structure)

## 2. Infrastructure & Workflow Rules
Execution Flow:
1. User uploads file to AWS S3 Raw Bucket.
2. S3 triggers an Object Created Event sending a notification to SQS stage-1-parsing.
3. KEDA monitors SQS Stage 1 and scales up Kubernetes ScaledJob (Haystack Chunker).
4. Chunker parses the document into text chunks and pushes a JSON array payload directly to SQS stage-2-indexing (Bypassing S3 to eliminate API transaction costs).
5. KEDA monitors SQS Stage 2 and scales up Kubernetes ScaledJob (Haystack Indexer).
6. Indexer requests embeddings from TEI and executes an idempotent gRPC upsert to Qdrant VectorDB.

Zero-Daemon Policy: Neither the chunker nor the indexer application MUST run as a continuous worker or background daemon. They are short-lived Kubernetes Jobs that wake up via KEDA, process their respective SQS tasks, and immediately terminate with exit code 0 to ensure absolute zero idle compute costs on AWS Spot Instances.

Security (Strict): ZERO hardcoded AWS credentials. Do not use .env files for AWS access keys. Authentication must be handled entirely via IAM Roles for Service Accounts (IRSA) attached to the Kubernetes ServiceAccounts.


## 3. Application Constraints
Python Chunker (apps/chunker/)
- Framework: Haystack for document parsing pipelines.
- Parsing (Strategy Pattern): Parsing logic MUST follow the Strategy Pattern. Define a common interface in parsers/base.py.
- Allowed Formats: Support ONLY 3 formats: PDF, TXT, and Markdown. No heavy, generic wrappers (e.g., do not use unstructured).
- Data Contract: Must ensure that the generated array of text chunks + metadata packed into the SQS Stage 2 message strictly fits within the 256 KB SQS payload limit. Split across multiple messages if a document is too large.

Python Indexer (apps/indexer/)
- Framework: Haystack for embedding and indexing pipelines.
- Idempotency Policy: Must generate deterministic Point IDs for Qdrant using a cryptographic hash of the source metadata (e.g., UUID5(file_name + chunk_index)). This guarantees that if an AWS Spot instance is evicted mid-job, a retry will result in an overwrite rather than vector duplication.

Go API (apps/api/)
- Purpose: A minimalist API layer for serving frontend charts, dashboards, and executing low-latency synchronous semantic queries against VectorDB. 
- Stack: Use the Go standard library (net/http) or an ultra-lightweight router (e.g., go-chi). Do not use heavy enterprise frameworks. Maximize memory efficiency.

Terraform (terraform/)
- Write clean, modular, and reusable infrastructure-as-code.
- Every AWS resource must be explicitly tagged with Project = "simple-rag".

## 4. AI Assistant Directives
Keep it Lean: If an engineering problem can be solved natively without adding a new third-party dependency, do it. Extra dependencies translate directly to larger Docker images and higher Spot billing limits.

Production-Ready Code: Skip placeholders, // TODO comments, or dummy mock data unless explicitly requested. Provide complete, valid, and lint-clean code snippets.

Observability: Since the indexer runs as a detached, ephemeral Kube Job, implement clear, structured logging to stdout (JSON format preferred) for fast CloudWatch debugging.

## 5. Current Status
### Current Timeline & Target
- Phase: Local PoC / Infrastructure Design
- Current Focus: Selection of Embedding models, and contract definitions for Chunker, Indexer, and Go API.

### Accepted ADRs
- [ADR-0004: Using SQS Payload to Transfer Document Chunks] Status: Accepted.

### Current Tech Stack
- Frontend: Single HTML (Vanilla JS) served by Go.
- Ingestion (Stage 1): S3 -> SQS (stage-1-parsing) -> KEDA -> K8s ScaledJob (Python/Haystack Chunker).
- Ingestion (Stage 2): SQS (stage-2-indexing payload) -> KEDA -> K8s ScaledJob (Python/Haystack Indexer).
- VectorDB: Qdrant (Self-hosted in Kubernetes, gRPC integration).
- Query Layer: Go API (Read-Only access to Qdrant).

### Current Blockers / Tasks to Discuss
- Embedding model selection (e.g., Text Embeddings Inference configuration), and strict JSON schema definition for the SQS Stage 2 chunk payload.
- Decide about AI framework Haystack vs LangChain for the chunker and indexer. Haystack is currently favored for its out-of-the-box document parsing and embedding pipeline capabilities, but LangChain could offer more flexibility if we need to implement custom logic later on.
