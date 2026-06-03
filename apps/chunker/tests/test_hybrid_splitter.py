from haystack.dataclasses import Document
from src.hybrid_splitter import HybridDocumentSplitter

def test_hybrid_document_splitter_empty():
    splitter = HybridDocumentSplitter(max_tokens=10, overlap_tokens=2)
    result = splitter.run(documents=[])
    assert result == {"documents": []}

def test_hybrid_document_splitter_short_text():
    splitter = HybridDocumentSplitter(max_tokens=15, overlap_tokens=2)
    docs = [Document(content="Short text for testing splitter.", meta={"key": "val"})]
    result = splitter.run(documents=docs)
    
    assert len(result["documents"]) == 1
    assert result["documents"][0].content == "Short text for testing splitter."
    assert result["documents"][0].meta["key"] == "val"
    assert result["documents"][0].meta["chunk_index"] == 0

def test_hybrid_document_splitter_split_text():
    splitter = HybridDocumentSplitter(max_tokens=5, overlap_tokens=1)
    text = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10"
    docs = [Document(content=text, meta={"key": "val"})]
    result = splitter.run(documents=docs)
    
    splitted_docs = result["documents"]
    assert len(splitted_docs) > 1
    
    tokenizer = splitter.tokenizer
    for doc in splitted_docs:
        tokens_count = len(tokenizer.encode(doc.content))
        assert tokens_count <= 5
        assert doc.meta["key"] == "val"
        assert "chunk_index" in doc.meta
