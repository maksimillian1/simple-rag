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
