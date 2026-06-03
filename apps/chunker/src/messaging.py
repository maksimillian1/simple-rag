import json
import logging

logger = logging.getLogger("chunker")

# Constants
BATCH_SIZE = 40

def get_sqs_client():
    """
    Construct SQS client using environment configurations.
    """
    import boto3
    from . import config
    
    sqs_endpoint = config.AWS_ENDPOINT_URL
    region = config.AWS_DEFAULT_REGION
    aws_access_key = config.AWS_ACCESS_KEY_ID
    aws_secret_key = config.AWS_SECRET_ACCESS_KEY

    kwargs = {}
    if aws_access_key:
        kwargs["aws_access_key_id"] = aws_access_key
    if aws_secret_key:
        kwargs["aws_secret_access_key"] = aws_secret_key

    return boto3.client(
        "sqs",
        region_name=region,
        endpoint_url=sqs_endpoint,
        **kwargs
    )

def parse_message_body(message: dict) -> dict | None:
    body_str = message["Body"]
    try:
        return json.loads(body_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON body from message: {e}")
        return None

def is_s3_test_event(body: dict) -> bool:
    if body.get("Event") == "s3:TestEvent":
        logger.info(f"Received Amazon S3 TestEvent notification for bucket '{body.get('Bucket')}'. Safely deleting message.")
        return True
    return False

def extract_s3_coords(body: dict) -> tuple | None:
    bucket_name = None
    object_key = None
    object_size = None

    if "Records" in body:
        try:
            record = body["Records"][0]
            bucket_name = record["s3"]["bucket"]["name"]
            from urllib.parse import unquote_plus
            object_key = unquote_plus(record["s3"]["object"]["key"])
            object_size = record["s3"]["object"].get("size")
        except (KeyError, IndexError) as e:
            logger.error(f"Malformed S3 Notification event structure: {e}")
    elif "bucket" in body and "key" in body:
        bucket_name = body["bucket"]
        object_key = body["key"]
        object_size = body.get("size")

    if not bucket_name or not object_key:
        return None
    return bucket_name, object_key, object_size

def send_stage_2_batches(sqs_client, stage_2_queue_url: str, chunks, file_id: str, file_name: str, checksum: str) -> bool:
    import uuid
    import math
    
    total_chunks = len(chunks)
    total_parts = math.ceil(total_chunks / BATCH_SIZE)
    
    for i in range(0, total_chunks, BATCH_SIZE):
        batch_chunks = chunks[i:i + BATCH_SIZE]
        part_index = i // BATCH_SIZE
        
        payload_chunks = []
        for idx, chunk in enumerate(batch_chunks):
            global_index = i + idx
            payload_chunks.append({
                "chunk_index": global_index,
                "page_number": chunk.meta.get("page_number", 1),
                "content": chunk.content
            })
            
        stage_2_message = {
            "trace_id": str(uuid.uuid4()),
            "document": {
                "file_id": file_id,
                "file_name": file_name,
                "checksum": checksum
            },
            "boundaries": {
                "part_index": part_index,
                "total_parts": total_parts
            },
            "chunks": payload_chunks
        }
        
        try:
            logger.info(f"Pushing chunk batch {part_index + 1} ({len(payload_chunks)} chunks, index {i} to {i+len(payload_chunks)-1}) to SQS Stage 2...")
            sqs_client.send_message(
                QueueUrl=stage_2_queue_url,
                MessageBody=json.dumps(stage_2_message)
            )
        except Exception as e:
            logger.error(f"Failed to send batch of chunks to Stage 2 queue: {e}")
            return False
            
    return True
