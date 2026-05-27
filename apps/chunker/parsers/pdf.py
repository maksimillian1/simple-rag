from typing import List
from haystack import Document
from parsers.base import BaseParser
from pypdf import PdfReader

class PDFParser(BaseParser):
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
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
