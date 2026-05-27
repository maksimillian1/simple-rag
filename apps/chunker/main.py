import os
import sys
import json
import uuid
import tempfile
import signal
import logging
import boto3
from urllib.parse import unquote_plus
from haystack.components.preprocessors import DocumentSplitter

# Import parsing strategies
from parsers.txt import TXTParser
from parsers.markdown import MarkdownParser
from parsers.pdf import PDFParser

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

def get_boto_clients():
    """
    Construct SQS and S3 clients using environment configurations.
    """
    sqs_endpoint = os.getenv("AWS_ENDPOINT_URL")
    s3_endpoint = os.getenv("AWS_S3_ENDPOINT_URL")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    # Fallback to local mock credentials if endpoints are defined to prevent NoCredentialsError
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if (sqs_endpoint or s3_endpoint) and not aws_access_key:
        aws_access_key = "mock"
        aws_secret_key = "mock"

    sqs_client = boto3.client(
        "sqs",
        region_name=region,
        endpoint_url=sqs_endpoint,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key
    )

    s3_client = boto3.client(
        "s3",
        region_name=region,
        endpoint_url=s3_endpoint,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key
    )

    return sqs_client, s3_client

def resolve_parser(file_name: str):
    """
    Strategy Pattern Router. Matches file extensions to parsing strategies.
    """
    ext = os.path.splitext(file_name.lower())[1]
    if ext == ".txt":
        return TXTParser()
    elif ext == ".md":
        return MarkdownParser()
    elif ext in [".pdf"]:
        return PDFParser()
    else:
        raise ValueError(f"Unsupported file format: {ext}")

def main():
    global graceful_exit

    # Get environment variables
    queue_url = os.getenv("AWS_SQS_STAGE_1_URL")
    stage_2_queue_url = os.getenv("AWS_SQS_STAGE_2_URL")

    # Document Splitter configuration
    split_by = os.getenv("CHUNK_BY", "word")
    split_length = int(os.getenv("CHUNK_SIZE", "200"))
    split_overlap = int(os.getenv("CHUNK_OVERLAP", "20"))
    respect_sentence_boundary = os.getenv("CHUNK_RESPECT_SENTENCE", "true").lower() == "true"

    if not queue_url or not stage_2_queue_url:
        logger.error("AWS_SQS_STAGE_1_URL and AWS_SQS_STAGE_2_URL must be configured.")
        sys.exit(1)

    logger.info("Initializing SQS and S3 clients...")
    try:
        sqs_client, s3_client = get_boto_clients()
    except Exception as e:
        logger.error(f"Failed to initialize AWS clients: {e}")
        sys.exit(1)

    # Initialize Haystack DocumentSplitter
    logger.info(f"Initializing Haystack DocumentSplitter (split_by={split_by}, size={split_length}, overlap={split_overlap})")
    splitter = DocumentSplitter(
        split_by=split_by,
        split_length=split_length,
        split_overlap=split_overlap,
        respect_sentence_boundary=respect_sentence_boundary
    )

    logger.info("Starting Ephemeral Chunker Worker Loop...")

    while not graceful_exit:
        try:
            # Poll SQS with long polling (20 seconds) to minimize API cost & idle resources
            logger.info("Polling SQS Stage 1 queue...")
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10  # Long poll
            )

            messages = response.get("Messages", [])
            if not messages:
                continuous_poll = os.getenv("CONTINUOUS_POLL", "false").lower() == "true"
                if continuous_poll:
                    logger.info("No messages in Stage 1 queue. Sleeping 5 seconds for continuous polling...")
                    import time
                    time.sleep(5)
                    continue
                else:
                    logger.info("No messages in Stage 1 queue. Exiting (Queue drained cleanly).")
                    break

            message = messages[0]
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
                continue

            # Support both S3 Notification Envelope (Records) and developer-friendly direct events {"bucket": "...", "key": "..."}
            bucket_name = None
            object_key = None

            if "Records" in body:
                try:
                    record = body["Records"][0]
                    bucket_name = record["s3"]["bucket"]["name"]
                    # S3 event keys are URL-encoded, we must decode them to avoid download failures
                    object_key = unquote_plus(record["s3"]["object"]["key"])
                except (KeyError, IndexError) as e:
                    logger.error(f"Malformed S3 Notification event structure: {e}")
            elif "bucket" in body and "key" in body:
                bucket_name = body["bucket"]
                object_key = body["key"]

            if not bucket_name or not object_key:
                logger.error(f"Could not extract bucket name or object key from message body: {body_str}")
                sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                continue

            if bucket_name == "local":
                logger.info(f"Local bypass active: using local filesystem file directly: {object_key}")
            else:
                logger.info(f"S3 Object Target: s3://{bucket_name}/{object_key}")

            # Download file to a secure local temp directory
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
                    # Allow visibility timeout to reset so the job can retry on transient failures
                    continue

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
                    # Deleting immediately to prevent poisoned messages from locking queue
                    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                    continue
                except Exception as e:
                    logger.error(f"Critical error parsing and chunking file {file_name}: {e}")
                    # Retrying via visibility timeout
                    continue

                # Prepare the chunks payload and push in batches of up to 40 chunks
                # This ensures the message payload fits comfortably inside SQS 256KB limits
                success = True
                batch_size = 40
                total_chunks = len(chunks)

                for i in range(0, total_chunks, batch_size):
                    batch_chunks = chunks[i:i + batch_size]
                    
                    # Build structured Stage 2 Payload message
                    payload_chunks = []
                    for idx, chunk in enumerate(batch_chunks):
                        global_index = i + idx
                        payload_chunks.append({
                            "chunk_index": global_index,
                            "text": chunk.content
                        })

                    stage_2_message = {
                        "file_name": file_name,
                        "metadata": doc_metadata,
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

        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {e}")
            # Prevent fast-looping crash in case of continuous SQS connectivity failures
            import time
            time.sleep(5)

    logger.info("Chunker worker terminated cleanly.")

if __name__ == "__main__":
    main()
