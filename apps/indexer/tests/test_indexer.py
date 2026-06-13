import uuid
import numpy as np
from src.vector import generate_point_id, NAMESPACE_RAG

def test_point_id_generation():
    file_name = "annual_report_2026.pdf"
    chunk_idx = 14
    
    composite_key = f"{file_name}:{chunk_idx}"
    expected_uuid = str(uuid.uuid5(NAMESPACE_RAG, composite_key))
    
    actual_uuid = generate_point_id(file_name, chunk_idx)
    assert actual_uuid == expected_uuid

class MockSparseEmbeddingResult:
    def __init__(self, indices, values):
        self.indices = np.array(indices)
        self.values = np.array(values)

class MockSparseTextEmbedding:
    def __init__(self, model_name):
        self.model_name = model_name

    def embed(self, texts):
        for i, _ in enumerate(texts):
            yield MockSparseEmbeddingResult([100 + i, 200 + i], [0.1 + i, 0.2 + i])

def test_splade_document_processor():
    from src.haystack_pipeline import SpladeDocumentProcessor
    from haystack import Document

    mock_model = MockSparseTextEmbedding("test-model")
    processor = SpladeDocumentProcessor(splade_model=mock_model)
    docs = [
        Document(content="Hello world", meta={"file_name": "test.pdf", "chunk_index": 0}),
        Document(content="Another text", meta={"file_name": "test.pdf", "chunk_index": 1})
    ]

    result = processor.run(docs)
    processed_docs = result["documents"]

    assert len(processed_docs) == 2
    assert processed_docs[0].id == generate_point_id("test.pdf", 0)
    assert processed_docs[0].sparse_embedding.indices == [100, 200]
    assert processed_docs[0].sparse_embedding.values == [0.1, 0.2]
    assert processed_docs[1].id == generate_point_id("test.pdf", 1)
    assert processed_docs[1].sparse_embedding.indices == [101, 201]
    assert processed_docs[1].sparse_embedding.values == [1.1, 1.2]

def test_build_haystack_pipeline(monkeypatch):
    from src import config
    monkeypatch.setattr(config, "EMBEDDING_MODEL_TEI_URL", "http://localhost:8080")
    monkeypatch.setattr(config, "QDRANT_HOST", "localhost")
    monkeypatch.setattr(config, "QDRANT_PORT", 6334)
    monkeypatch.setattr(config, "COLLECTION_NAME", "test_collection")

    from src.haystack_pipeline import build_haystack_pipeline
    mock_model = MockSparseTextEmbedding("test-model")
    pipeline = build_haystack_pipeline(splade_model=mock_model)
    assert pipeline is not None
    assert "splade_processor" in pipeline.graph.nodes
    assert "embedder" in pipeline.graph.nodes
    assert "writer" in pipeline.graph.nodes
