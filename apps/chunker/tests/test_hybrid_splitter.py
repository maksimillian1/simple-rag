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

def test_hybrid_document_splitter_page_tracking():
    # Test sentence-level page tracking when splitting across page boundaries.
    # We want a chunk that starts on page 1 and ends on page 2, plus a second chunk on page 2.
    splitter = HybridDocumentSplitter(max_tokens=5, overlap_tokens=0)
    
    docs = [
        Document(content="WordA WordB WordC.", meta={"page_number": 1, "doc_id": "123"}),
        Document(content="WordD WordE. WordF WordG.", meta={"page_number": 2, "doc_id": "123"})
    ]
    
    result = splitter.run(documents=docs)
    splitted_docs = result["documents"]
    
    # We expect 2 chunks:
    # 1) "WordA WordB WordC.\n\n WordD WordE." -> page_number: 1 (starts on page 1, ends on page 2)
    # 2) "WordF WordG." -> page_number: 2 (starts on page 2)
    assert len(splitted_docs) == 2
    
    assert splitted_docs[0].content == "WordA WordB WordC.\n\n WordD WordE."
    assert splitted_docs[0].meta["page_number"] == 1
    assert splitted_docs[0].meta["doc_id"] == "123"
    assert splitted_docs[0].meta["chunk_index"] == 0
    
    assert splitted_docs[1].content == "WordE. WordF WordG."
    assert splitted_docs[1].meta["page_number"] == 2
    assert splitted_docs[1].meta["doc_id"] == "123"
    assert splitted_docs[1].meta["chunk_index"] == 1

def test_hybrid_document_splitter_oversized_sentence():
    # Test a sentence that is longer than max_tokens.
    # It should be split at word-level using _safe_word_split.
    splitter = HybridDocumentSplitter(max_tokens=3, overlap_tokens=0)
    
    docs = [Document(content="WordA WordB WordC WordD.", meta={"page_number": 1})]
    result = splitter.run(documents=docs)
    splitted_docs = result["documents"]
    
    # "WordA WordB WordC WordD." has 4 tokens in MockTokenizer.
    # max_tokens is 3. So it splits into 2 chunks with a 1-word overlap fallback:
    # 1) "WordA WordB WordC" (3 tokens)
    # 2) "WordC WordD." (2 tokens due to overlap)
    assert len(splitted_docs) == 2
    assert splitted_docs[0].content == "WordA WordB WordC"
    assert splitted_docs[0].meta["page_number"] == 1
    assert splitted_docs[1].content == "WordC WordD."
    assert splitted_docs[1].meta["page_number"] == 1

def test_hybrid_document_splitter_sentence_spans_pages():
    # A single sentence starting on page 1 and ending on page 2.
    # Because of page-level extraction, they are separate documents in the input list.
    # But they fit in the same chunk since max_tokens is large enough.
    splitter = HybridDocumentSplitter(max_tokens=10, overlap_tokens=0)
    
    docs = [
        Document(content="Sentence starts on page one", meta={"page_number": 1}),
        Document(content="and ends on page two.", meta={"page_number": 2})
    ]
    
    result = splitter.run(documents=docs)
    splitted_docs = result["documents"]
    
    # Both documents fit within max_tokens=10.
    # So we get 1 chunk combining both pages.
    # The chunk's page_number is 1 (starts on page 1).
    assert len(splitted_docs) == 1
    assert splitted_docs[0].content == "Sentence starts on page one\n\n and ends on page two."
    assert splitted_docs[0].meta["page_number"] == 1

def test_hybrid_document_splitter_complex_dots():
    # Test how splitter handles abbreviations/complex cases with dots like "Mr." or "f.e."
    # Since we do not handle them specially, they split into separate sentences.
    splitter = HybridDocumentSplitter(max_tokens=10, overlap_tokens=0)
    
    text = "Mr. Smith went home. This is f.e. a test."
    docs = [Document(content=text, meta={"page_number": 1})]
    
    result = splitter.run(documents=docs)
    splitted_docs = result["documents"]
    
    # Let's inspect the split sentences by looking at the content.
    # RE_SENTENCE_SPLIT splits at dot followed by space.
    # So the sentences are:
    # 1) "Mr."
    # 2) "Smith went home."
    # 3) "This is f.e."
    # 4) "a test."
    # Since max_tokens = 10, they all fit in a single chunk.
    # We verify the combined text of the chunk:
    assert len(splitted_docs) == 1
    assert splitted_docs[0].content == "Mr. Smith went home. This is f.e. a test."
    
    # Let's test with small max_tokens to see them split into separate chunks
    splitter_small = HybridDocumentSplitter(max_tokens=2, overlap_tokens=0)
    result_small = splitter_small.run(documents=docs)
    splitted_small = result_small["documents"]
    
    # Sentences and their MockTokenizer token lengths:
    # "Mr." -> 1 token
    # "Smith went home." -> 3 tokens
    # "This is f.e." -> 3 tokens
    # "a test." -> 2 tokens
    # Note: "Smith went home." exceeds max_tokens=2 and splits into:
    # - "Smith went" (2 tokens)
    # - "home." (1 token)
    # Let's verify that we have multiple chunks because of abbreviation sentence splits.
    assert len(splitted_small) > 1
