from typing import List
from haystack import Document
from parsers.base import BaseParser

class MarkdownParser(BaseParser):
    def parse(self, file_path: str, metadata: dict) -> List[Document]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        page_meta = metadata.copy()
        page_meta["page_number"] = 1
        return [Document(content=text, meta=page_meta)]
