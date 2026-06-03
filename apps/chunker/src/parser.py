import os
from abc import ABC, abstractmethod
from typing import List
from haystack import Document

class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        """
        Parses a file and returns a list of Haystack Document objects.
        """
        pass

class TXTParser(BaseParser):
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        page_meta = metadata.copy()
        page_meta["page_number"] = 1
        return [Document(content=text, meta=page_meta)]

class MarkdownParser(BaseParser):
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        page_meta = metadata.copy()
        page_meta["page_number"] = 1
        return [Document(content=text, meta=page_meta)]

class PDFParser(BaseParser):
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        documents = []
        for idx, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                # Create a shallow copy to prevent sharing across pages
                page_meta = metadata.copy()
                page_meta["page_number"] = idx + 1
                documents.append(Document(content=text, meta=page_meta))
        return documents

def resolve_parser(file_name: str):
    """
    Strategy Pattern Router. Matches file extensions to parsing strategies.
    Uses lazy loading of parsers to avoid importing heavy parser libraries unless used.
    """
    ext = os.path.splitext(file_name.lower())[1]
    if ext == ".txt":
        return TXTParser()
    elif ext == ".md":
        return MarkdownParser()
    elif ext in [".pdf"]:
        return PDFParser()
    else:
        raise ValueError(f"Unsupported file format: {ext}")
