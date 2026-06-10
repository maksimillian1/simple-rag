import re
import uuid
import zlib
from collections import Counter

NAMESPACE_RAG = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')

def generate_point_id(file_name: str, chunk_index: int) -> str:
    """
    Generates a completely deterministic UUIDv5 Point ID for Qdrant.
    This guarantees that Spot evictions and retries are idempotent.
    """
    composite_key = f"{file_name}:{chunk_index}"
    return str(uuid.uuid5(NAMESPACE_RAG, composite_key))

def compute_sparse_vector(text: str) -> dict:
    """
    Compute a deterministic sparse vector representation of the text.
    Word tokens are mapped to positive 32-bit integers using zlib.adler32,
    and weights are calculated using normalized term frequencies.
    """
    words = re.findall(r'\b[a-zA-Z0-9]{2,}\b', text.lower())
    if not words:
        return {"indices": [], "values": []}
    
    counts = Counter(words)
    total_words = len(words)
    
    sparse_data = []
    for word, count in counts.items():
        word_index = zlib.adler32(word.encode('utf-8')) & 0x7fffffff
        weight = float(count) / total_words
        sparse_data.append((word_index, weight))
    
    # Sort by index ascending (Qdrant requirement)
    sparse_data.sort(key=lambda x: x[0])
    
    indices = [item[0] for item in sparse_data]
    values = [round(item[1], 4) for item in sparse_data]
    
    return {
        "indices": indices,
        "values": values
    }
