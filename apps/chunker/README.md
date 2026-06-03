# Chunker Application

Stage 1: Ephemeral parsing and chunking job for `simple-rag`. It pulls messages from SQS, downloads files from S3, parses them using TXT, Markdown, or PDF parsers, chunks them using a custom `HybridDocumentSplitter` Haystack component, and pushes chunks to SQS Stage 2 queue.

## Project Structure

```
apps/chunker/
├── .gitignore
├── pyproject.toml
├── README.md
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── core.py
│   ├── hybrid_splitter.py
│   ├── messaging.py
│   ├── parser.py
│   └── storage.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_core.py
    ├── test_hybrid_splitter.py
    ├── test_messaging.py
    ├── test_parser.py
    └── test_storage.py
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

4. **Run the chunker worker**:
   ```bash
   chunker
   ```
