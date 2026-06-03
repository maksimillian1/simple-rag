import os
import tempfile
import hashlib
import pytest
from unittest.mock import MagicMock, patch
from haystack.dataclasses import Document

from src.core import calculate_sha256, process_message

def test_calculate_sha256():
    content = b"test checksum logic"
    expected_hash = hashlib.sha256(content).hexdigest()
    
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(content)
        temp_file_path = temp_file.name
        
    try:
        actual_hash = calculate_sha256(temp_file_path)
        assert actual_hash == expected_hash
    finally:
        os.remove(temp_file_path)

@patch("src.core.download_file_to_local")
@patch("src.core.parse_and_split")
def test_process_message_success(mock_parse_split, mock_download):
    mock_sqs = MagicMock()
    mock_s3 = MagicMock()
    mock_splitter = MagicMock()
    
    msg = {
        "ReceiptHandle": "rh-1",
        "MessageId": "mid-1",
        "Body": '{"bucket": "b", "key": "test.txt", "size": 10}'
    }
    
    chunks = [Document(content="chunk text", meta={"page_number": 1})]
    mock_parse_split.return_value = (chunks, "doc_123", "checksum_abc")
    
    with patch("src.core.send_stage_2_batches") as mock_send_batches:
        mock_send_batches.return_value = True
        
        res_splitter, res_s3 = process_message(
            msg,
            mock_sqs,
            mock_s3,
            "https://stage-1-url",
            "https://stage-2-url",
            mock_splitter
        )
        
    assert res_splitter == mock_splitter
    assert res_s3 == mock_s3
    
    mock_sqs.delete_message.assert_called_once_with(
        QueueUrl="https://stage-1-url",
        ReceiptHandle="rh-1"
    )
