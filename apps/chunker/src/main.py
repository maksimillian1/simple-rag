import os
import sys
import tempfile
import signal
import logging
import time
import hashlib

from . import config
from .parser import resolve_parser
from .messaging import (
    get_sqs_client,
    parse_message_body,
    is_s3_test_event,
    extract_s3_coords,
    send_stage_2_batches
)
from .storage import (
    get_s3_client,
    validate_object_size,
    download_file_to_local
)

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("chunker")

# Constants
MAX_ALLOWED_SIZE_BYTES = 104857600  # 100MB
POLL_WAIT_TIME_SECONDS = 10
POLL_SLEEP_INTERVAL_SECONDS = 5
ERROR_SLEEP_INTERVAL_SECONDS = 5

# Signal handling for AWS Spot instance eviction
graceful_exit = False

def handle_signal(signum, frame):
    global graceful_exit
    logger.info(f"Signal {signum} received. Finishing current message and shutting down...")
    graceful_exit = True

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

def calculate_sha256(file_path: str) -> str:
    """
    Calculate SHA256 hex checksum of a local file.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_splitter():
    logger.info("Initializing ProperTokenHybridSplitter (lazy loading)...")
    from .hybrid_splitter import ProperTokenHybridSplitter
    return ProperTokenHybridSplitter(
        max_tokens=config.CHUNK_SIZE,
        overlap_tokens=config.CHUNK_OVERLAP
    )

def parse_and_split(temp_file_path: str, file_name: str, bucket_name: str, object_key: str, splitter):
    logger.info(f"Resolving parser strategy for: {file_name}")
    parser = resolve_parser(file_name)
    
    doc_metadata = {
        "bucket": bucket_name,
        "key": object_key,
        "file_name": file_name
    }
    
    logger.info("Executing text extraction strategy...")
    documents = parser.parse(temp_file_path, doc_metadata)
    
    logger.info("Executing ProperTokenHybridSplitter...")
    split_result = splitter.run(documents=documents)
    chunks = split_result["documents"]
    logger.info(f"Document split into {len(chunks)} chunks.")
    
    checksum = calculate_sha256(temp_file_path)
    file_id = f"doc_{checksum[:8]}"
    logger.info(f"Generated file_id: {file_id} with checksum: {checksum}")
    
    return chunks, file_id, checksum

def write_debug_chunks(chunks, file_id: str, file_name: str, checksum: str, debug_dir: str) -> None:
    try:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_filename = "".join(c for c in file_name if c.isalnum() or c in "._-").strip()
        dynamic_folder_name = f"{timestamp}-{clean_filename}"
        
        target_debug_dir = os.path.join(debug_dir, dynamic_folder_name)
        os.makedirs(target_debug_dir, exist_ok=True)
        
        logger.info(f"Dumping {len(chunks)} chunks to dynamic DEBUG_DIR: {target_debug_dir}...")
        for idx, chunk in enumerate(chunks):
            page_number = chunk.meta.get("page_number", 1)
            debug_file_path = os.path.join(target_debug_dir, f"{file_id}_chunk_{idx:04d}.txt")
            with open(debug_file_path, "w", encoding="utf-8") as f:
                f.write("--- METADATA ---\n")
                f.write(f"File Name: {file_name}\n")
                f.write(f"File ID: {file_id}\n")
                f.write(f"Checksum: {checksum}\n")
                f.write(f"Chunk Index: {idx}\n")
                f.write(f"Page Number: {page_number}\n")
                f.write("----------------\n\n")
                f.write(chunk.content)
        logger.info("Successfully dumped chunks to DEBUG_DIR.")
    except Exception as e:
        logger.error(f"Failed to dump debug chunks to {debug_dir}: {e}")

def process_message(message: dict, sqs_client, s3_client, queue_url: str, stage_2_queue_url: str, splitter):
    """
    Process a single Stage 1 chunking task:
    1. Parses message and extracts coordinates.
    2. Downloads payload file from S3 to temp location.
    3. Runs parsing and document splitting.
    4. Submits chunk batches to SQS Stage 2.
    5. Deletes source message from Stage 1 queue.
    """
    receipt_handle = message["ReceiptHandle"]
    body = parse_message_body(message)
    if not body or is_s3_test_event(body):
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return splitter, s3_client

    coords = extract_s3_coords(body)
    if not coords or not validate_object_size(coords[0], coords[1], coords[2], MAX_ALLOWED_SIZE_BYTES):
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return splitter, s3_client
    bucket_name, object_key, _ = coords

    if bucket_name != "local" and s3_client is None:
        logger.info("Initializing S3 client (lazy loading)...")
        try:
            s3_client = get_s3_client()
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            return splitter, None

    if splitter is None:
        splitter = get_splitter()

    file_name = os.path.basename(object_key)
    
    import contextlib
    if bucket_name == "local":
        temp_file_path = object_key
        ctx = contextlib.nullcontext()
    else:
        temp_dir = tempfile.TemporaryDirectory()
        temp_file_path = os.path.join(temp_dir.name, file_name)
        ctx = temp_dir

    with ctx:
        if bucket_name != "local":
            try:
                download_file_to_local(s3_client, bucket_name, object_key, temp_file_path)
            except Exception as e:
                logger.error(f"Failed to access/download file: {e}")
                return splitter, s3_client

        try:
            chunks, file_id, checksum = parse_and_split(temp_file_path, file_name, bucket_name, object_key, splitter)
        except ValueError as e:
            logger.error(f"Unsupported format error: {e}")
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
            return splitter, s3_client
        except Exception as e:
            logger.error(f"Critical error parsing and chunking file {file_name}: {e}")
            return splitter, s3_client

        debug_dir = os.getenv("DEBUG_DIR")
        if debug_dir:
            write_debug_chunks(chunks, file_id, file_name, checksum, debug_dir)

        success = send_stage_2_batches(sqs_client, stage_2_queue_url, chunks, file_id, file_name, checksum)
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
            logger.info("Polling SQS Stage 1 queue...")
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=POLL_WAIT_TIME_SECONDS
            )

            messages = response.get("Messages", [])
            if not messages:
                if config.CONTINUOUS_POLL:
                    logger.info("No messages in Stage 1 queue. Sleeping 5 seconds for continuous polling...")
                    time.sleep(POLL_SLEEP_INTERVAL_SECONDS)
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
            time.sleep(ERROR_SLEEP_INTERVAL_SECONDS)

    logger.info("Chunker worker terminated cleanly.")

if __name__ == "__main__":
    main()
