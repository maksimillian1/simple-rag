import uuid
import zlib
from src.vector import generate_point_id, compute_sparse_vector, NAMESPACE_RAG

def test_point_id_generation():
    file_name = "annual_report_2026.pdf"
    chunk_idx = 14
    
    composite_key = f"{file_name}:{chunk_idx}"
    expected_uuid = str(uuid.uuid5(NAMESPACE_RAG, composite_key))
    
    actual_uuid = generate_point_id(file_name, chunk_idx)
    assert actual_uuid == expected_uuid

def test_sparse_vector_computation():
    text = "Financial growth growth Q1"
    
    res = compute_sparse_vector(text)
    indices = res["indices"]
    values = res["values"]
    
    assert len(indices) == 3
    assert len(values) == 3
    
    h_financial = zlib.adler32(b"financial") & 0x7fffffff
    h_growth = zlib.adler32(b"growth") & 0x7fffffff
    h_q1 = zlib.adler32(b"q1") & 0x7fffffff
    
    expected_pairs = sorted([
        (h_financial, 0.25),
        (h_growth, 0.50),
        (h_q1, 0.25)
    ], key=lambda x: x[0])
    
    expected_indices = [p[0] for p in expected_pairs]
    expected_values = [p[1] for p in expected_pairs]
    
    assert indices == expected_indices
    assert values == expected_values

def test_sparse_vector_empty_or_no_valid_words():
    res = compute_sparse_vector("")
    assert res == {"indices": [], "values": []}

    res2 = compute_sparse_vector("a b c I")
    assert res2 == {"indices": [], "values": []}

def test_sparse_vector_case_insensitivity_and_punctuation():
    text = "Growth, growth! Growth."
    res = compute_sparse_vector(text)
    h_growth = zlib.adler32(b"growth") & 0x7fffffff
    assert res["indices"] == [h_growth]
    assert res["values"] == [1.0]

def test_build_haystack_pipeline(monkeypatch):
    from src import config
    monkeypatch.setattr(config, "EMBEDDING_MODEL_TEI_URL", "http://localhost:8080")
    monkeypatch.setattr(config, "QDRANT_HOST", "localhost")
    monkeypatch.setattr(config, "QDRANT_PORT", 6334)
    monkeypatch.setattr(config, "COLLECTION_NAME", "test_collection")

    from src.main import build_haystack_pipeline
    pipeline = build_haystack_pipeline()
    assert pipeline is not None
    assert "embedder" in pipeline.graph.nodes
    assert "writer" in pipeline.graph.nodes
