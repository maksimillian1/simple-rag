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

        raw_pages: List[str] = []
        with fitz.open(file_path) as doc:
            for page in doc:
                page_text = self._extract_page_text(page)
                raw_pages.append(page_text)

        processed_text = self._merge_pages_with_hyphen_migration(raw_pages)

        combined_meta = metadata.copy()
        combined_meta["page_number"] = DEFAULT_PAGE_NUM
        return [Document(content=processed_text, meta=combined_meta)]

    def _extract_page_text(self, page) -> str:
        blocks = page.get_text("blocks")
        page_pieces = []
        for b in blocks:
            block_text = b[4].strip()
            if block_text:
                page_pieces.append(block_text)

        raw_text = " ".join(page_pieces)
        # Fix inline intra-page hyphens immediately
        clean_text = RE_LINE_HYPHEN.sub('', raw_text)
        return RE_MULTIPLE_SPACES.sub(' ', clean_text).strip()

    def _merge_pages_with_hyphen_migration(self, pages: List[str]) -> str:
        """
        Advanced page stitching algorithm. If a page ends with a hyphenated half-word,
        it cuts it out, shifts it to the next page, and glues it back together.
        This preserves structural integrity and keeps page markers accurate for the UI.
        """
        final_pieces: List[str] = []
        carry_over_word = ""

        for idx, page_text in enumerate(pages):
            page_num = idx + 1

            if carry_over_word and page_text:
                # Prepend the carried over partial word to the first word of the next page
                first_space_idx = page_text.find(" ")
                if first_space_idx != -1:
                    first_word = page_text[:first_space_idx]
                    rest_of_page = page_text[first_space_idx:]
                    glued_word = (carry_over_word + first_word).replace("-", "")
                    page_text = glued_word + rest_of_page
                else:
                    page_text = (carry_over_word + page_text).replace("-", "")
                carry_over_word = ""

            page_text, carry_over_word = self._extract_trailing_hyphen(page_text)

            if page_text.strip() or carry_over_word:
                final_pieces.append(f"__PAGE_{page_num}__ {page_text.strip()}")

        complete_text = " ".join(final_pieces)
        return RE_MULTIPLE_SPACES.sub(' ', complete_text).strip()

    def _extract_trailing_hyphen(self, text: str) -> Tuple[str, str]:
        match = RE_TRAILING_HYPHEN_WORD.search(text)
        if match:
            hyphen_word = match.group(1)
            clean_text = text[:match.start()].strip()
            return clean_text, hyphen_word
        return text, ""

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
