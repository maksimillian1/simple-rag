import sys
from typing import List
from haystack import component, Document, Pipeline
from haystack.dataclasses import SparseEmbedding

from . import config
from .vector import generate_point_id

_SHARED_SPLADE_MODEL = None

def get_splade_model(model_name: str) -> SparseTextEmbedding:
    global _SHARED_SPLADE_MODEL
    if _SHARED_SPLADE_MODEL is None:
        _SHARED_SPLADE_MODEL = SparseTextEmbedding(model_name=model_name)
    return _SHARED_SPLADE_MODEL

@component
class SpladeDocumentProcessor:
    def __init__(self, model_name: str = config.SPLADE_MODEL_NAME):
        self.model_name = model_name

    @component.output_types(documents=List[Document])
    def run(self, documents: List[Document]) -> dict:
        model = get_splade_model(self.model_name)

        texts = [doc.content for doc in documents if doc.content]
        if texts:
            embeddings = list(model.embed(texts))
            emb_iter = iter(embeddings)
        else:
            emb_iter = iter([])

        processed_docs = []
        for doc in documents:
            file_name = doc.meta.get("file_name", "unknown")
            chunk_index = doc.meta.get("chunk_index", 0)
            deterministic_id = generate_point_id(file_name, chunk_index)

            sparse_embedding = None
            if doc.content:
                try:
                    sparse_res = next(emb_iter)
                    sparse_embedding = SparseEmbedding(
                        indices=sparse_res.indices.tolist(),
                        values=[round(val, 4) for val in sparse_res.values.tolist()]
                    )
                except StopIteration:
                    pass

            processed_doc = Document(
                id=deterministic_id,
                content=doc.content,
                meta=doc.meta,
                sparse_embedding=sparse_embedding
            )
            processed_docs.append(processed_doc)

        return {"documents": processed_docs}

def build_haystack_pipeline():
    from haystack.components.embedders import HuggingFaceAPIDocumentEmbedder
    from haystack.components.writers import DocumentWriter
    from haystack_integrations.document_stores.qdrant import QdrantDocumentStore

    pipeline = Pipeline()

    pipeline.add_component("splade_processor", SpladeDocumentProcessor())

    pipeline.add_component("embedder", HuggingFaceAPIDocumentEmbedder(
        api_type=config.TEI_API_TYPE,
        api_params={"url": config.EMBEDDING_MODEL_TEI_URL}
    ))

    document_store = QdrantDocumentStore(
        host=config.QDRANT_HOST,
        port=config.QDRANT_PORT,
        index=config.COLLECTION_NAME,
        prefer_grpc=config.QDRANT_PREFER_GRPC,
        use_sparse_embeddings=True,
        embedding_dim=config.DENSE_EMBEDDING_DIM
    )

    pipeline.add_component("writer", DocumentWriter(document_store=document_store))

    pipeline.connect("splade_processor.documents", "embedder.documents")
    pipeline.connect("embedder.documents", "writer.documents")
    return pipeline
