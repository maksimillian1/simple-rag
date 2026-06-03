import re
from typing import List, Dict, Any
from haystack import component
from haystack.dataclasses import Document

DEFAULT_MAX_TOKENS = 300
DEFAULT_OVERLAP_TOKENS = 50
DEFAULT_LLAMA_MODEL = "Xenova/llama3-tokenizer-base"

RE_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')
RE_MULTIPLE_SPACES = re.compile(r' +')
RE_PAGE_MARKER = re.compile(r'__PAGE_(\d+)__')

@component
class HybridDocumentSplitter:
    """
    Haystack 2.0 component for recursive hybrid text splitting
    with semantic boundaries, page tracking, and Llama 3.1 tokenization.
    """
    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
        model_name: str = DEFAULT_LLAMA_MODEL
    ):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.model_name = model_name
        self._tokenizer = None

    @property
    def tokenizer(self):
        """Lazy loading of the HuggingFace tokenizer tailored for Llama 3.1"""
        if self._tokenizer is None:
            from transformers import AutoTokenizer
            # Downloads only the tiny tokenizer config (~4MB), no model weights
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        return self._tokenizer

    @component.output_types(documents=List[Document])
    def run(self, documents: List[Document]) -> Dict[str, Any]:
        if not documents:
            return {"documents": []}

        processed_docs = []
        for doc in documents:
            if not doc.content or not isinstance(doc.content, str):
                continue

            cleaned_text = self._prepare_text(doc.content)
            chunks = self._split_into_chunks(cleaned_text)

            for i, chunk in enumerate(chunks):
                processed_docs.append(self._build_document(doc, chunk, i))

        return {"documents": processed_docs}

    def _prepare_text(self, text: str) -> str:
        text = text.replace("\n\n", "===PARAGRAPH===")
        text = text.replace("\n", " ")
        text = text.replace("===PARAGRAPH===", "\n\n")
        return RE_MULTIPLE_SPACES.sub(' ', text).strip()

    def _build_document(self, parent_doc: Document, chunk_text: str, index: int) -> Document:
        page_match = RE_PAGE_MARKER.search(chunk_text)
        chunk_page = parent_doc.meta.get("page_number", 1)
        if page_match:
            chunk_page = int(page_match.group(1))

        clean_content = RE_PAGE_MARKER.sub('', chunk_text)
        clean_content = RE_MULTIPLE_SPACES.sub(' ', clean_content).strip()

        new_meta = {
            **parent_doc.meta,
            "chunk_index": index,
            "page_number": chunk_page
        }
        return Document(content=clean_content, meta=new_meta)

    def _split_into_chunks(self, text: str) -> List[str]:
        paragraphs = text.split("\n\n")
        all_sentences = []

        for para in paragraphs:
            if not para.strip():
                continue
            sentences = [s.strip() for s in RE_SENTENCE_SPLIT.split(para) if s.strip()]
            all_sentences.extend(sentences)
            if all_sentences:
                all_sentences[-1] += "\n\n"

        chunks, current_chunk = [], []
        current_tokens = 0

        for sentence in all_sentences:
            sentence_tokens = len(self.tokenizer.encode(sentence))

            if sentence_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(" ".join(current_chunk).strip())
                    current_chunk, current_tokens = [], 0

                sub_chunks = self._safe_word_split(sentence)
                chunks.extend(sub_chunks[:-1])
                last_piece = sub_chunks[-1]
                current_chunk = [last_piece]
                current_tokens = len(self.tokenizer.encode(last_piece))
                continue

            if current_tokens + sentence_tokens > self.max_tokens:
                chunks.append(" ".join(current_chunk).strip())
                overlap_chunk = self._build_overlap_sentences(current_chunk)
                current_chunk = overlap_chunk + [sentence]
                current_tokens = sum(len(self.tokenizer.encode(s)) for s in current_chunk)
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens

        if current_chunk:
            chunks.append(" ".join(current_chunk).strip())
        return chunks

    def _build_overlap_sentences(self, current_chunk: List[str]) -> List[str]:
        overlap_chunk = []
        overlap_tokens_count = 0
        for s in reversed(current_chunk):
            s_t = len(self.tokenizer.encode(s))
            if overlap_tokens_count + s_t > self.overlap_tokens:
                break
            overlap_chunk.insert(0, s)
            overlap_tokens_count += s_t

        if not overlap_chunk and current_chunk:
            last_sentence = current_chunk[-1]
            overlap_chunk = [self._extract_last_words_by_tokens(last_sentence, self.overlap_tokens)]
        return overlap_chunk

    def _safe_word_split(self, text: str) -> List[str]:
        words = text.split()
        sub_chunks, current_words = [], []

        for word in words:
            current_words.append(word)
            if len(self.tokenizer.encode(" ".join(current_words))) > self.max_tokens:
                if len(current_words) > 1:
                    current_words.pop()
                sub_chunks.append(" ".join(current_words))

                overlap_words = []
                for w in reversed(current_words):
                    overlap_words.insert(0, w)
                    if len(self.tokenizer.encode(" ".join(overlap_words))) >= self.overlap_tokens:
                        break
                current_words = overlap_words + [word]

        if current_words:
            sub_chunks.append(" ".join(current_words))
        return sub_chunks

    def _extract_last_words_by_tokens(self, text: str, target_tokens: int) -> str:
        words = text.split()
        extracted_words = []
        for word in reversed(words):
            extracted_words.insert(0, word)
            if len(self.tokenizer.encode(" ".join(extracted_words))) > target_tokens:
                if len(extracted_words) > 1:
                    extracted_words.pop(0)
                break
        return " ".join(extracted_words)
