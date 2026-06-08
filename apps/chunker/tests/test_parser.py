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
    mock_doc = MagicMock()
    mock_page1 = MagicMock()
    mock_page1.get_text.return_value = [
        (0, 0, 100, 100, "This is a read-", 0, 0)
    ]
    mock_page2 = MagicMock()
    mock_page2.get_text.return_value = [
        (0, 0, 100, 100, "ing list.", 0, 0)
    ]
    
    # Mock fitz document behaves as a context manager and page iterator
    mock_doc.__enter__.return_value = mock_doc
    mock_doc.__iter__.return_value = [mock_page1, mock_page2]
    
    # Mock fitz.open class/method
    monkeypatch.setattr("fitz.open", lambda path: mock_doc)
    
    parser = PDFParser()
    docs = parser.parse("dummy_path.pdf", {"bucket": "test-bucket", "key": "test.pdf"})
    
    assert len(docs) == 2
    assert docs[0].content == "This is a reading"
    assert docs[0].meta["page_number"] == 1
    assert docs[0].meta["bucket"] == "test-bucket"
    assert docs[0].meta["key"] == "test.pdf"
    
    assert docs[1].content == "list."
    assert docs[1].meta["page_number"] == 2
    assert docs[1].meta["bucket"] == "test-bucket"
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

def test_pdf_parser_edge_cases(monkeypatch):
    mock_doc = MagicMock()
    # Mock three pages:
    # Page 1: ends with a hyphen, next page is empty.
    # Page 2: empty page.
    # Page 3: ends with a hyphen, no next page.
    mock_page1 = MagicMock()
    mock_page1.get_text.return_value = [
        (0, 0, 100, 100, "This is pageone-", 0, 0)
    ]
    mock_page2 = MagicMock()
    mock_page2.get_text.return_value = []
    
    mock_page3 = MagicMock()
    mock_page3.get_text.return_value = [
        (0, 0, 100, 100, "This is pagethree-", 0, 0)
    ]

    mock_doc.__enter__.return_value = mock_doc
    mock_doc.__iter__.return_value = [mock_page1, mock_page2, mock_page3]
    monkeypatch.setattr("fitz.open", lambda path: mock_doc)

    parser = PDFParser()
    docs = parser.parse("dummy_path.pdf", {"bucket": "test-bucket", "key": "test.pdf"})

    # Since page 2 is empty, it should be ignored (not included in output docs).
    # docs[0] corresponds to Page 1: "This is pageone" (hyphen stripped, no gluing since page 2 is empty).
    # docs[1] corresponds to Page 3: "This is pagethree" (hyphen stripped, no gluing since it is the last page).
    assert len(docs) == 2
    assert docs[0].content == "This is pageone"
    assert docs[0].meta["page_number"] == 1
    assert docs[1].content == "This is pagethree"
    assert docs[1].meta["page_number"] == 3
