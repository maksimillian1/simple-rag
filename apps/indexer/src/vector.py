import uuid

# Standard DNS namespace UUID for deterministic UUIDv5 generation
NAMESPACE_RAG = uuid.NAMESPACE_DNS

def generate_point_id(file_name: str, chunk_index: int) -> str:
    """
    Generates a completely deterministic UUIDv5 Point ID for Qdrant.
    This guarantees that Spot evictions and retries are idempotent.
    """
    composite_key = f"{file_name}:{chunk_index}"
    return str(uuid.uuid5(NAMESPACE_RAG, composite_key))
