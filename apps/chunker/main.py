import os
import sys
import json
import uuid
import tempfile
import signal
import logging
import math
import time
import boto3

import config
from utils import calculate_sha256, resolve_parser

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("chunker")

# Signal handling for AWS Spot instance eviction
graceful_exit = False

def handle_signal(signum, frame):
    global graceful_exit
    logger.info(f"Signal {signum} received. Finishing current message and shutting down...")
    graceful_exit = True

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

def get_sqs_client():
    """
    Construct SQS client using environment configurations.
    """
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

def get_s3_client():
    """
    Construct S3 client using environment configurations.
    """
    s3_endpoint = config.AWS_S3_ENDPOINT_URL
    region = config.AWS_DEFAULT_REGION
    aws_access_key = config.AWS_ACCESS_KEY_ID
    aws_secret_key = config.AWS_SECRET_ACCESS_KEY

    kwargs = {}
    if aws_access_key:
        kwargs["aws_access_key_id"] = aws_access_key
    if aws_secret_key:
        kwargs["aws_secret_access_key"] = aws_secret_key

    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=s3_endpoint,
        **kwargs
    )

def process_message(message: dict, sqs_client, s3_client, queue_url: str, stage_2_queue_url: str, splitter):
    """
    Process a single Stage 1 chunking task:
    1. Parses message to extract S3 bucket and key.
    2. Lazily initializes S3 Client and DocumentSplitter.
    3. Downloads S3 object to local temporary file.
    4. Parses file into document representation using strategy pattern.
    5. Splits documents into semantic chunks using Haystack.
    6. Formats Stage 2 message payloads.
    7. Pushes chunk batches of size 40 to SQS Stage 2 queue.
    8. Deletes Stage 1 SQS message on success.
    Returns (splitter, s3_client) to preserve lazy initialized states.
    """
    receipt_handle = message["ReceiptHandle"]
    body_str = message["Body"]

    logger.info(f"Processing message ID: {message['MessageId']}")

    # Parse message payload
    try:
        body = json.loads(body_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON body from message: {e}")
        # Delete corrupted message immediately to avoid loop bottlenecks
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return splitter, s3_client

    # Gracefully ignore and delete S3 test events to avoid error logging noise
    if body.get("Event") == "s3:TestEvent":
        logger.info(f"Received Amazon S3 TestEvent notification for bucket '{body.get('Bucket')}'. Safely deleting message.")
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return splitter, s3_client

    # Extract target S3 coordinates (supports standard S3 Notification Envelope and developer direct format)
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
        logger.error(f"Could not extract bucket name or object key from message body: {body_str}")
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return splitter, s3_client

    # Enforce 100MB size limit guard to prevent OOM
    MAX_ALLOWED_SIZE_BYTES = 104857600  # 100MB
    if bucket_name == "local":
        try:
            if os.path.exists(object_key):
                object_size = os.path.getsize(object_key)
        except Exception as e:
            logger.warning(f"Failed to resolve file size for local path {object_key}: {e}")

    if object_size is not None and object_size > MAX_ALLOWED_SIZE_BYTES:
        logger.warning(f"File too large ({object_size} bytes). Aborting download path. Limit is {MAX_ALLOWED_SIZE_BYTES} bytes.")
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return splitter, s3_client

    # Lazily initialize S3 Client if not local and not initialized yet
    if bucket_name != "local" and s3_client is None:
        logger.info("Initializing S3 client (lazy loading)...")
        try:
            s3_client = get_s3_client()
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            return splitter, None

    # Lazily initialize Haystack DocumentSplitter
    if splitter is None:
        logger.info("Initializing Haystack DocumentSplitter (lazy loading)...")
        from haystack.components.preprocessors import DocumentSplitter
        splitter = DocumentSplitter(
            split_by=config.CHUNK_BY,
            split_length=config.CHUNK_SIZE,
            split_overlap=config.CHUNK_OVERLAP,
            respect_sentence_boundary=config.CHUNK_RESPECT_SENTENCE
        )

    file_name = os.path.basename(object_key)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = os.path.join(temp_dir, file_name)
        
        try:
            if bucket_name == "local":
                temp_file_path = object_key
            else:
                logger.info(f"Downloading s3://{bucket_name}/{object_key} to local temporary storage...")
                s3_client.download_file(bucket_name, object_key, temp_file_path)
        except Exception as e:
            logger.error(f"Failed to access/download file: {e}")
            # Reset visibility timeout so the job can retry on transient failures
            return splitter, s3_client

        # Parse the file using Strategy Pattern
        try:
            logger.info(f"Resolving parser strategy for: {file_name}")
            parser = resolve_parser(file_name)
            
            # Prepare document metadata
            doc_metadata = {
                "bucket": bucket_name,
                "key": object_key,
                "file_name": file_name
            }
            
            logger.info("Executing text extraction strategy...")
            documents = parser.parse(temp_file_path, doc_metadata)
            
            # Splicing document text into semantic chunks
            logger.info("Executing Haystack DocumentSplitter...")
            split_result = splitter.run(documents=documents)
            chunks = split_result["documents"]
            logger.info(f"Document split into {len(chunks)} chunks.")

        except ValueError as e:
            logger.error(f"Unsupported format error: {e}")
            # Delete immediately to prevent poisoned messages from locking queue
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
            return splitter, s3_client
        except Exception as e:
            logger.error(f"Critical error parsing and chunking file {file_name}: {e}")
            return splitter, s3_client

        # Calculate document checksum and file_id for the deterministic contract
        try:
            checksum = calculate_sha256(temp_file_path)
            file_id = f"doc_{checksum[:8]}"
            logger.info(f"Generated file_id: {file_id} with checksum: {checksum}")
        except Exception as e:
            logger.error(f"Failed to calculate checksum for {file_name}: {e}")
            return splitter, s3_client

        # Dump chunks locally if DEBUG_DIR is set
        debug_dir = os.getenv("DEBUG_DIR")
        if debug_dir:
            try:
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                # Clean up filename for safe folder naming
                clean_filename = "".join(c for c in file_name if c.isalnum() or c in "._-").strip()
                dynamic_folder_name = f"{timestamp}-{clean_filename}"
                
                target_debug_dir = os.path.join(debug_dir, dynamic_folder_name)
                os.makedirs(target_debug_dir, exist_ok=True)
                
                logger.info(f"Dumping {len(chunks)} chunks to dynamic DEBUG_DIR: {target_debug_dir}...")
                for idx, chunk in enumerate(chunks):
                    chunk_index = idx
                    page_number = chunk.meta.get("page_number", 1)
                    debug_file_path = os.path.join(target_debug_dir, f"{file_id}_chunk_{chunk_index:04d}.txt")
                    with open(debug_file_path, "w", encoding="utf-8") as f:
                        f.write("--- METADATA ---\n")
                        f.write(f"File Name: {file_name}\n")
                        f.write(f"File ID: {file_id}\n")
                        f.write(f"Checksum: {checksum}\n")
                        f.write(f"Chunk Index: {chunk_index}\n")
                        f.write(f"Page Number: {page_number}\n")
                        f.write("----------------\n\n")
                        f.write(chunk.content)
                logger.info("Successfully dumped chunks to DEBUG_DIR.")
            except Exception as e:
                logger.error(f"Failed to dump debug chunks to {debug_dir}: {e}")

        # Prepare the chunks payload and push in batches of up to 40 chunks
        success = True
        batch_size = 40
        total_chunks = len(chunks)
        total_parts = math.ceil(total_chunks / batch_size)

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            part_index = i // batch_size
            
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
                logger.info(f"Pushing chunk batch {i//batch_size + 1} ({len(payload_chunks)} chunks, index {i} to {i+len(payload_chunks)-1}) to SQS Stage 2...")
                sqs_client.send_message(
                    QueueUrl=stage_2_queue_url,
                    MessageBody=json.dumps(stage_2_message)
                )
            except Exception as e:
                logger.error(f"Failed to send batch of chunks to Stage 2 queue: {e}")
                success = False
                break

        if success:
            logger.info(f"Successfully processed s3://{bucket_name}/{object_key}. Deleting message from Stage 1 queue...")
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        else:
            logger.error(f"S3 file s3://{bucket_name}/{object_key} was partially processed. SQS message left in queue for retries.")

    return splitter, s3_client

def main():
    global graceful_exit

    # Validate Queue Configs
    queue_url = config.AWS_SQS_STAGE_1_URL
    stage_2_queue_url = config.AWS_SQS_STAGE_2_URL

    if not queue_url or not stage_2_queue_url:
        logger.error("AWS_SQS_STAGE_1_URL and AWS_SQS_STAGE_2_URL must be configured.")
        sys.exit(1)

    logger.info("Initializing SQS client...")
    try:
        sqs_client = get_sqs_client()
    except Exception as e:
        logger.error(f"Failed to initialize SQS client: {e}")
        sys.exit(1)

    s3_client = None
    splitter = None

    logger.info("Starting Ephemeral Chunker Worker Loop...")

    while not graceful_exit:
        try:
            # Poll SQS with long polling (10 seconds)
            logger.info("Polling SQS Stage 1 queue...")
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10  # Long poll
            )

            messages = response.get("Messages", [])
            if not messages:
                if config.CONTINUOUS_POLL:
                    logger.info("No messages in Stage 1 queue. Sleeping 5 seconds for continuous polling...")
                    time.sleep(5)
                    continue
                else:
                    logger.info("No messages in Stage 1 queue. Exiting (Queue drained cleanly).")
                    break

            # Process the received message
            splitter, s3_client = process_message(
                messages[0], 
                sqs_client, 
                s3_client, 
                queue_url, 
                stage_2_queue_url, 
                splitter
            )

        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {e}")
            time.sleep(5)

    logger.info("Chunker worker terminated cleanly.")

if __name__ == "__main__":
    main()
