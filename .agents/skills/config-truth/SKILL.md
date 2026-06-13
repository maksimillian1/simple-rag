---
name: config-truth
description: Single source of truth for the project's environment variables, configuration parameters, and AWS/local endpoints. Use this skill when writing, refactoring, or running the code to ensure configuration alignment.
---

# Project Configuration Single Source of Truth

## 1. Core Principles
- **No Speculative Config**: Do not invent new configuration variables or assume different default values.
- **Reference Existing Env Files**: Always inspect `.env` before modifying configuration parsing code.
- **Unified Sourcing**: Any changes to endpoints must be updated in `.env` files first.

## 2. Critical Vector & LLM Parameters
- `DENSE_VECTORS_NAME`: `text-dense` (Model: `BAAI/bge-small-en-v1.5` via TEI).
- `SPARSE_VECTORS_NAME`: `text-sparse` (Model: `fastembed.SPLADE_PP_ED8R` / `Qdrant/Splade_PP_en_v1`). **DO NOT use any custom hashing/Adler32 functions for sparse vectors.**
- `LLM_PROVIDER`: `bedrock`
- `MODEL_ID`: `us.meta.llama3-1-8b-instruct-v1:0` (Requires correct prompt formatting. Do not mix Llama 3.0 tokens with Llama 3.1+ inference block).

## 3. Network & Environment Nuances
- **Local Host Mode**: Services connect via `localhost` (e.g., `QDRANT_URL=http://localhost:6333`, `TEI_URL=http://localhost:8081`).
- **Container Mode (Docker Compose / KEDA)**: Workers use container-native routing:
  - `INDEXER_QDRANT_HOST=qdrant`
  - `INDEXER_EMBEDDING_MODEL_TEI_URL=http://tei-embeddings:80`

## 4. AWS / SQS Specifics
- `AWS_BEDROCK_REGION`: Always explicitly target `us-east-1` for Bedrock clients (with fallback to `AWS_DEFAULT_REGION`).
- `AWS_ENDPOINT_URL`: Used ONLY for offline ElasticMQ testing. Go API must dynamically bypass this parameter if the target queue is a live AWS SQS URL (`AWS_IGNORE_CONFIGURED_ENDPOINT_URLS=true`).

## 5. Implementation Locations
- **Go API**: Parsed in `apps/api/core/config.go` via `LoadConfig()`.
- **Python Workers**: Read directly via `os.getenv()` in `config.py`. Continuous polling is controlled by `CHUNKER_CONTINUOUS_POLL` and `INDEXER_CONTINUOUS_POLL`.
- In local dev mode, relies on env files mounted/passed through shell.
- In `docker-compose.yml`, utilizes `env_file: - .env` for configuration parity.
