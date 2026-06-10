# Indexer Application

Stage 2: Ephemeral indexing job for `simple-rag`. It pulls chunks from SQS Stage 2, processes them to generate deterministic IDs, computes sparse embedding vectors using normalized term frequency (Adler-32 hashes), generates dense embeddings using TEI (`BAAI/bge-small-en-v1.5`), and indexes documents into Qdrant using the declarative Haystack 2.0 Ingestion Pipeline.

## Project Structure

```
apps/indexer/
├── pyproject.toml
├── README.md
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   └── vector.py
└── tests/
    ├── __init__.py
    └── test_indexer.py
```

## Installation & Running

1. **Set up virtual environment (optional but recommended)**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install package in editable mode with dev dependencies**:
   > [!NOTE]
   > Double quotes are required around `.[dev]` on shells like `zsh` to prevent wildcard expansion errors.
   ```bash
   pip install -e ".[dev]"
   ```

3. **Run unit tests**:
   ```bash
   pytest
   ```

4. **Run the indexer worker**:
   ```bash
   indexer
   ```
