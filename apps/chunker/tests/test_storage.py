import os
import tempfile
import pytest
from unittest.mock import MagicMock

from src.storage import validate_object_size, download_file_to_local

def test_validate_object_size():
    # Under limit
    assert validate_object_size("b", "k", 100, 200) is True
    # Over limit
    assert validate_object_size("b", "k", 300, 200) is False

def test_validate_object_size_local():
    content = b"some content"
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(content)
        temp_file_path = temp_file.name
        
    try:
        # Under limit local file
        assert validate_object_size("local", temp_file_path, None, 20) is True
        # Over limit local file
        assert validate_object_size("local", temp_file_path, None, 5) is False
    finally:
        os.remove(temp_file_path)

def test_download_file_to_local():
    mock_s3 = MagicMock()
    # Should call download_file on client
    download_file_to_local(mock_s3, "test-bucket", "test-key", "local-path")
    mock_s3.download_file.assert_called_once_with("test-bucket", "test-key", "local-path")
    
    # Should not call download_file if bucket is local
    mock_s3.reset_mock()
    download_file_to_local(mock_s3, "local", "local-key", "local-path")
    mock_s3.download_file.assert_not_called()
