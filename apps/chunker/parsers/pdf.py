from typing import List
from haystack import Document
from parsers.base import BaseParser
from pypdf import PdfReader

class PDFParser(BaseParser):
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        reader = PdfReader(file_path)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
        
        full_text = "\n\n".join(pages_text)
        return [Document(content=full_text, meta=metadata)]
