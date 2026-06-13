import os
import re
from abc import ABC, abstractmethod
from typing import List, Tuple
from haystack import Document

DEFAULT_PAGE_NUM = 1
ENCODING_UTF8 = "utf-8"
ERRORS_IGNORE = "ignore"

EXT_TXT = ".txt"
EXT_MD = ".md"
EXT_PDF = ".pdf"

# Matches word hyphenation at the end of a line (e.g., "read-\n").
RE_LINE_HYPHEN = re.compile(r'-\s*\n+')
# Matches any sequence of multiple spaces.
RE_MULTIPLE_SPACES = re.compile(r' +')
# Matches trailing hyphenated word at the very end of a string (e.g., "word- ").
RE_TRAILING_HYPHEN_WORD = re.compile(r'(\b\w+-)\s*$')

class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        """
        Parses a file and returns a list containing a single Document with combined text.
        """
        pass

class TXTParser(BaseParser):
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        with open(file_path, "r", encoding=ENCODING_UTF8, errors=ERRORS_IGNORE) as f:
            text = f.read()

        page_meta = metadata.copy()
        page_meta["page_number"] = DEFAULT_PAGE_NUM
        return [Document(content=text.strip(), meta=page_meta)]

class MarkdownParser(BaseParser):
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        with open(file_path, "r", encoding=ENCODING_UTF8, errors=ERRORS_IGNORE) as f:
            text = f.read()

        page_meta = metadata.copy()
        page_meta["page_number"] = DEFAULT_PAGE_NUM
        return [Document(content=text.strip(), meta=page_meta)]

class PDFParser(BaseParser):
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        import fitz

        # Get raw pages text
        with fitz.open(file_path) as doc:
            raw_pages = [self._extract_page_text(page) for page in doc]

        # Normalize text breaks across and within pages
        normalized_pages = self._normalize_text_on_pages(raw_pages)

        # Prepare a List of Documents for each page
        documents = []
        for idx, page_text in enumerate(normalized_pages):
            if page_text.strip():
                page_meta = metadata.copy()
                page_meta["page_number"] = idx + 1
                documents.append(Document(content=page_text.strip(), meta=page_meta))

        return documents

    def _extract_page_text(self, page) -> str:
        blocks = page.get_text("blocks")
        return " ".join(b[4] for b in blocks if b[4])

    def _normalize_text_on_pages(self, pages: List[str]) -> List[str]:
        """
        Normalizes page texts:
        1. Cleans intra-page line-end hyphens and collapses spaces.
        2. Glues inter-page boundary hyphenated words by pulling the continuation backward.
        """
        # Step 1: Clean intra-page line breaks and multiple spaces
        cleaned = []
        for text in pages:
            clean_text = RE_LINE_HYPHEN.sub("", text)
            cleaned.append(RE_MULTIPLE_SPACES.sub(" ", clean_text).strip())

        # Step 2: Glue inter-page boundary hyphenated words
        for idx in range(len(cleaned)):
            page_text = cleaned[idx]
            match = RE_TRAILING_HYPHEN_WORD.search(page_text)
            if not match:
                continue

            hyphen_prefix = match.group(1)
            next_idx = idx + 1
            has_next = next_idx < len(cleaned) and cleaned[next_idx]

            if has_next:
                next_page_text = cleaned[next_idx]
                parts = next_page_text.split(" ", 1)
                first_word = parts[0]
                rest_of_next_page = parts[1] if len(parts) > 1 else ""

                glued_word = (hyphen_prefix + first_word).replace("-", "")
                cleaned[idx] = (page_text[:match.start()].strip() + " " + glued_word).strip()
                cleaned[next_idx] = rest_of_next_page.strip()
            else:
                glued_word = hyphen_prefix.replace("-", "")
                cleaned[idx] = (page_text[:match.start()].strip() + " " + glued_word).strip()

        return cleaned

def resolve_parser(file_name: str) -> BaseParser:
    """
    Strategy Pattern Router. Matches file extensions to parsing strategies.
    """
    ext = os.path.splitext(file_name.lower())[1]
    if ext == EXT_TXT:
        return TXTParser()
    elif ext == EXT_MD:
        return MarkdownParser()
    elif ext == EXT_PDF:
        return PDFParser()
    else:
        raise ValueError(f"Unsupported file format: {ext}")
