import re
from typing import List, Dict, Any
from haystack import component
from haystack.dataclasses import Document

DEFAULT_MAX_WORDS = 250
DEFAULT_OVERLAP_WORDS = 40

SEPARATORS = [
    r"\n\n+",
    r"\n",
    r"(?<=[.!?]) +",
    r"(?<=[,;]) +",
    r" "
]

@component
class HybridDocumentSplitter:
    """
    Haystack 2.0 component for recursive hybrid text splitting
    with semantic boundaries and strict word limits.
    """

    def __init__(self, max_words: int = DEFAULT_MAX_WORDS, overlap: int = DEFAULT_OVERLAP_WORDS):
        self.max_words = max_words
        self.overlap = overlap

    @component.output_types(documents=List[Document])
    def run(self, documents: List[Document]) -> Dict[str, Any]:
        if not documents:
            return {"documents": []}

        processed_docs = []
        for doc in documents:
            if not doc.content or not isinstance(doc.content, str):
                continue

            chunks = self._split_text(doc.content, SEPARATORS)
            for i, chunk in enumerate(chunks):
                processed_docs.append(Document(
                    content=chunk,
                    meta={**doc.meta, "chunk_index": i}
                ))

        return {"documents": processed_docs}

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        if len(text.split()) <= self.max_words:
            return [text]

        separator = separators[0] if separators else ""
        next_separators = separators[1:] if separators else []

        if separator:
            fragments = [f for f in re.split(separator, text) if f.strip()]
        else:
            fragments = list(text)

        if len(fragments) == 1:
            if next_separators:
                return self._split_text(text, next_separators)
            return self._hard_split_by_words(text)

        return self._merge_fragments(fragments, next_separators)

    def _compute_overlap(self, fragments: List[str]) -> List[str]:
        overlap_fragments = []
        overlap_words = 0
        for frag in reversed(fragments):
            frag_len = len(frag.split())
            if overlap_words + frag_len > self.overlap:
                break
            overlap_fragments.insert(0, frag)
            overlap_words += frag_len
        return overlap_fragments

    def _handle_oversized_fragment(self, frag: str, next_seps: List[str], current_chunks: List[str]) -> tuple:
        deep_chunks = self._split_text(frag, next_seps)
        current_chunks.extend(deep_chunks[:-1])
        last_chunk = deep_chunks[-1]
        return [last_chunk], len(last_chunk.split())

    def _merge_fragments(self, fragments: List[str], next_separators: List[str]) -> List[str]:
        chunks, current_frags = [], []
        current_words = 0

        for frag in fragments:
            frag_words = len(frag.split())

            if frag_words > self.max_words:
                if current_frags:
                    chunks.append(" ".join(current_frags).strip())
                current_frags, current_words = self._handle_oversized_fragment(frag, next_separators, chunks)
                continue

            if current_words + frag_words > self.max_words:
                if current_frags:
                    chunks.append(" ".join(current_frags).strip())
                current_frags = self._compute_overlap(current_frags) + [frag]
                current_words = sum(len(f.split()) for f in current_frags)
            else:
                current_frags.append(frag)
                current_words += frag_words

        if current_frags:
            chunks.append(" ".join(current_frags).strip())
        return chunks

    def _hard_split_by_words(self, text: str) -> List[str]:
        words = text.split()
        chunks = []
        step = self.max_words - self.overlap
        for i in range(0, len(words), step):
            chunks.append(" ".join(words[i:i + self.max_words]))
        return chunks
