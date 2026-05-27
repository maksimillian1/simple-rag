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
