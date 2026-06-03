from haystack.dataclasses import Document
from src.hybrid_splitter import HybridDocumentSplitter

def test_hybrid_document_splitter_empty():
    splitter = HybridDocumentSplitter(max_words=10, overlap=2)
    result = splitter.run(documents=[])
    assert result == {"documents": []}

def test_hybrid_document_splitter_short_text():
    splitter = HybridDocumentSplitter(max_words=10, overlap=2)
    docs = [Document(content="Short text with five words.", meta={"key": "val"})]
    result = splitter.run(documents=docs)
    
    assert len(result["documents"]) == 1
    assert result["documents"][0].content == "Short text with five words."
    assert result["documents"][0].meta["key"] == "val"
    assert result["documents"][0].meta["chunk_index"] == 0

def test_hybrid_document_splitter_split_text():
    splitter = HybridDocumentSplitter(max_words=5, overlap=1)
    text = "word1 word2 word3 word4 word5 word6 word7 word8"
    docs = [Document(content=text, meta={"key": "val"})]
    result = splitter.run(documents=docs)
    
    # Text split should result in multiple documents, each <= 5 words
    splitted_docs = result["documents"]
    assert len(splitted_docs) > 1
    for doc in splitted_docs:
        assert len(doc.content.split()) <= 5
        assert doc.meta["key"] == "val"
        assert "chunk_index" in doc.meta
