import os
import hashlib

def calculate_sha256(file_path: str) -> str:
    """
    Calculate SHA256 hex checksum of a local file.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def resolve_parser(file_name: str):
    """
    Strategy Pattern Router. Matches file extensions to parsing strategies.
    Uses lazy loading of parsers to avoid importing heavy parser libraries unless used.
    """
    ext = os.path.splitext(file_name.lower())[1]
    if ext == ".txt":
        from parsers.txt import TXTParser
        return TXTParser()
    elif ext == ".md":
        from parsers.markdown import MarkdownParser
        return MarkdownParser()
    elif ext in [".pdf"]:
        from parsers.pdf import PDFParser
        return PDFParser()
    else:
        raise ValueError(f"Unsupported file format: {ext}")
