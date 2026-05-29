import unittest
import uuid
import zlib
from main import generate_point_id, compute_sparse_vector, NAMESPACE_RAG

class TestIndexerLogic(unittest.TestCase):
    def test_point_id_generation(self):
        file_name = "annual_report_2026.pdf"
        chunk_idx = 14
        
        # Manually compute matching contracts.md rule: UUID5(NAMESPACE_RAG, "file_name:global_chunk_index")
        composite_key = f"{file_name}:{chunk_idx}"
        expected_uuid = str(uuid.uuid5(NAMESPACE_RAG, composite_key))
        
        actual_uuid = generate_point_id(file_name, chunk_idx)
        self.assertEqual(actual_uuid, expected_uuid)
        
    def test_sparse_vector_computation(self):
        text = "Financial growth growth Q1"
        # Token lower: "financial", "growth", "q1" (ignore length < 2 like 'q1'? No, length of 'q1' is 2, so it's included!)
        # Words found: ["financial", "growth", "growth", "q1"] -> total 4 words
        # counts: {"financial": 1, "growth": 2, "q1": 1}
        # expected weights (normalized):
        # financial: 1/4 = 0.25
        # growth: 2/4 = 0.50
        # q1: 1/4 = 0.25
        
        res = compute_sparse_vector(text)
        indices = res["indices"]
        values = res["values"]
        
        self.assertEqual(len(indices), 3)
        self.assertEqual(len(values), 3)
        
        # Adler32 hashes of words
        h_financial = zlib.adler32(b"financial") & 0x7fffffff
        h_growth = zlib.adler32(b"growth") & 0x7fffffff
        h_q1 = zlib.adler32(b"q1") & 0x7fffffff
        
        # The indices and values must be sorted by index ascending
        expected_pairs = sorted([
            (h_financial, 0.25),
            (h_growth, 0.50),
            (h_q1, 0.25)
        ], key=lambda x: x[0])
        
        expected_indices = [p[0] for p in expected_pairs]
        expected_values = [p[1] for p in expected_pairs]
        
        self.assertEqual(indices, expected_indices)
        self.assertEqual(values, expected_values)

if __name__ == '__main__':
    unittest.main()
