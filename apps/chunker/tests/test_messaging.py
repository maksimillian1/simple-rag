import json
import pytest
from unittest.mock import MagicMock, patch
from haystack.dataclasses import Document

from src.messaging import (
    parse_message_body,
    is_s3_test_event,
    extract_s3_coords,
    send_stage_2_batches
)

def test_parse_message_body():
    msg = {"Body": '{"key": "value"}'}
    assert parse_message_body(msg) == {"key": "value"}
    
    invalid_msg = {"Body": "invalid-json"}
    assert parse_message_body(invalid_msg) is None

def test_is_s3_test_event():
    test_body = {"Event": "s3:TestEvent", "Bucket": "my-bucket"}
    assert is_s3_test_event(test_body) is True
    
    normal_body = {"bucket": "my-bucket", "key": "file.txt"}
    assert is_s3_test_event(normal_body) is False

def test_extract_s3_coords_direct():
    body = {"bucket": "test-b", "key": "test-k", "size": 123}
    res = extract_s3_coords(body)
    assert res == ("test-b", "test-k", 123)

def test_extract_s3_coords_notification():
    body = {
        "Records": [{
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "folder%2Ffile.txt", "size": 456}
            }
        }]
    }
    res = extract_s3_coords(body)
    assert res == ("test-bucket", "folder/file.txt", 456)

def test_send_stage_2_batches():
    mock_sqs = MagicMock()
    chunks = [
        Document(content="c1", meta={"page_number": 1}),
        Document(content="c2", meta={"page_number": 1}),
        Document(content="c3", meta={"page_number": 2})
    ]
    
    # Temporarily set batch size to 2 to test batching
    with patch("src.config.BATCH_SIZE", 2):
        success = send_stage_2_batches(
            mock_sqs,
            "https://stage-2-url",
            chunks,
            "doc_1234",
            "file.txt",
            "sha256_val"
        )
        
    assert success is True
    assert mock_sqs.send_message.call_count == 2
    
    # Verify the first batch payload structure
    first_call_args = mock_sqs.send_message.call_args_list[0][1]
    body = json.loads(first_call_args["MessageBody"])
    assert body["document"]["file_id"] == "doc_1234"
    assert body["boundaries"]["part_index"] == 0
    assert body["boundaries"]["total_parts"] == 2
    assert len(body["chunks"]) == 2
    assert body["chunks"][0]["chunk_index"] == 0
    assert body["chunks"][0]["content"] == "c1"
    assert body["chunks"][0]["page_number"] == 1
    assert body["chunks"][1]["chunk_index"] == 1
    assert body["chunks"][1]["content"] == "c2"
