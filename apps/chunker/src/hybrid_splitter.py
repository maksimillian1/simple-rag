import re
from typing import List, Dict, Any
from haystack import component
from haystack.dataclasses import Document

DEFAULT_MAX_TOKENS = 300
DEFAULT_OVERLAP_TOKENS = 50
DEFAULT_LLAMA_MODEL = "unsloth/llama-3-8b-Instruct"

RE_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')
RE_MULTIPLE_SPACES = re.compile(r' +')

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

        all_sentences = self._extract_sentences(documents)
        chunks = self._split_into_chunks(all_sentences)
        processed_docs = self._build_documents_from_chunks(chunks, documents[0].meta)

        return {"documents": processed_docs}

    def _extract_sentences(self, documents: List[Document]) -> List[Dict[str, Any]]:
        """Extracts and cleans all sentences from input documents, tracking page numbers."""
        all_sentences = []
        for doc in documents:
            if not doc.content or not isinstance(doc.content, str):
                continue

            page_num = doc.meta.get("page_number", 1)
            cleaned_text = self._prepare_text(doc.content)
            paragraphs = cleaned_text.split("\n\n")

            for para in paragraphs:
                if not para.strip():
                    continue
                sentences = [s.strip() for s in RE_SENTENCE_SPLIT.split(para) if s.strip()]
                for s in sentences:
                    all_sentences.append({"text": s, "page_number": page_num})
                if all_sentences:
                    all_sentences[-1]["text"] += "\n\n"
        return all_sentences

    def _build_documents_from_chunks(self, chunks: List[Dict[str, Any]], base_meta: Dict[str, Any]) -> List[Document]:
        """Creates Document objects from chunks using a map approach."""
        return [
            Document(
                content=chunk["text"],
                meta=self._prepare_metadata(base_meta, idx, chunk["page_number"])
            )
            for idx, chunk in enumerate(chunks)
        ]

    def _prepare_metadata(self, base_meta: Dict[str, Any], index: int, page_number: int) -> Dict[str, Any]:
        """Prepares the metadata dictionary for a chunk document."""
        new_meta = base_meta.copy()
        new_meta["chunk_index"] = index
        new_meta["page_number"] = page_number
        return new_meta

    def _prepare_text(self, text: str) -> str:
        text = text.replace("\n\n", "===PARAGRAPH===")
        text = text.replace("\n", " ")
        text = text.replace("===PARAGRAPH===", "\n\n")
        return RE_MULTIPLE_SPACES.sub(' ', text).strip()

    def _create_chunk(self, sentences: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = " ".join(s["text"] for s in sentences).strip()
        text = RE_MULTIPLE_SPACES.sub(' ', text).strip()
        page_num = sentences[0]["page_number"] if sentences else 1
        return {"text": text, "page_number": page_num}

    def _split_into_chunks(self, all_sentences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chunks = []
        current_chunk = []
        current_tokens = 0

        for sent_info in all_sentences:
            sentence = sent_info["text"]
            page_num = sent_info["page_number"]
            sentence_tokens = len(self.tokenizer.encode(sentence))

            if sentence_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(self._create_chunk(current_chunk))
                    current_chunk = []
                    current_tokens = 0

                sub_chunks = self._safe_word_split(sentence)
                for piece in sub_chunks[:-1]:
                    chunks.append({"text": piece, "page_number": page_num})
                last_piece = sub_chunks[-1]
                current_chunk = [{"text": last_piece, "page_number": page_num}]
                current_tokens = len(self.tokenizer.encode(last_piece))
                continue

            if current_tokens + sentence_tokens > self.max_tokens:
                chunks.append(self._create_chunk(current_chunk))
                overlap_chunk = self._build_overlap_sentences(current_chunk)
                current_chunk = overlap_chunk + [sent_info]
                current_tokens = sum(len(self.tokenizer.encode(s["text"])) for s in current_chunk)
            else:
                current_chunk.append(sent_info)
                current_tokens += sentence_tokens

        if current_chunk:
            chunks.append(self._create_chunk(current_chunk))
        return chunks

    def _build_overlap_sentences(self, current_chunk: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        overlap_chunk = []
        overlap_tokens_count = 0
        for s_info in reversed(current_chunk):
            s = s_info["text"]
            s_t = len(self.tokenizer.encode(s))
            if overlap_tokens_count + s_t > self.overlap_tokens:
                break
            overlap_chunk.insert(0, s_info)
            overlap_tokens_count += s_t

        if not overlap_chunk and current_chunk:
            last_s_info = current_chunk[-1]
            last_sentence = last_s_info["text"]
            overlap_text = self._extract_last_words_by_tokens(last_sentence, self.overlap_tokens)
            overlap_chunk = [{"text": overlap_text, "page_number": last_s_info["page_number"]}]
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
