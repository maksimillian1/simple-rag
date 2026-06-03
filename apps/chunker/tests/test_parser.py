import os
import tempfile
from unittest.mock import MagicMock
import pytest

from src.parser import TXTParser, MarkdownParser, PDFParser, resolve_parser

def test_txt_parser():
    content = "Hello, this is standard text."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as temp_file:
        temp_file.write(content)
        temp_file_path = temp_file.name
        
    try:
        parser = TXTParser()
        docs = parser.parse(temp_file_path, {"bucket": "test-bucket", "key": "test.txt"})
        assert len(docs) == 1
        assert docs[0].content == content
        assert docs[0].meta["page_number"] == 1
        assert docs[0].meta["bucket"] == "test-bucket"
    finally:
        os.remove(temp_file_path)

def test_markdown_parser():
    content = "# Heading\n\n- item 1\n- item 2"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as temp_file:
        temp_file.write(content)
        temp_file_path = temp_file.name
        
    try:
        parser = MarkdownParser()
        docs = parser.parse(temp_file_path, {"bucket": "test-bucket", "key": "test.md"})
        assert len(docs) == 1
        assert docs[0].content == content
        assert docs[0].meta["page_number"] == 1
        assert docs[0].meta["bucket"] == "test-bucket"
    finally:
        os.remove(temp_file_path)

def test_pdf_parser(monkeypatch):
    mock_reader = MagicMock()
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Page 1 text content."
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page 2 text content."
    mock_reader.pages = [mock_page1, mock_page2]
    
    # Mock the PdfReader class to return our mock reader
    monkeypatch.setattr("pypdf.PdfReader", lambda path: mock_reader)
    
    parser = PDFParser()
    docs = parser.parse("dummy_path.pdf", {"bucket": "test-bucket", "key": "test.pdf"})
    
    assert len(docs) == 2
    assert docs[0].content == "Page 1 text content."
    assert docs[0].meta["page_number"] == 1
    assert docs[0].meta["bucket"] == "test-bucket"
    assert docs[1].content == "Page 2 text content."
    assert docs[1].meta["page_number"] == 2
    assert docs[1].meta["key"] == "test.pdf"

def test_resolve_parser_success():
    assert isinstance(resolve_parser("document.txt"), TXTParser)
    assert isinstance(resolve_parser("readme.md"), MarkdownParser)
    assert isinstance(resolve_parser("report.pdf"), PDFParser)
    assert isinstance(resolve_parser("upper_doc.TXT"), TXTParser)

def test_resolve_parser_failure():
    with pytest.raises(ValueError) as excinfo:
        resolve_parser("image.png")
    assert "Unsupported file format" in str(excinfo.value)
