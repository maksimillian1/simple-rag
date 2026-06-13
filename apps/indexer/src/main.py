import sys
import json
import signal
import logging
import time

from . import config
from .vector import generate_point_id
from .haystack_pipeline import SpladeDocumentProcessor, build_haystack_pipeline

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("indexer")

graceful_exit = False

def handle_signal(signum, frame):
    global graceful_exit
    logger.info(f"Signal {signum} received. Finishing current message and shutting down...")
    graceful_exit = True

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

def get_sqs_client():
    import boto3
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

def process_sqs_message(message_body: str, pipeline) -> bool:
    try:
        body = json.loads(message_body)
    except Exception as e:
        logger.error(f"Failed to parse JSON body from message: {e}")
        return True

    doc_block = body.get("document", {})
    file_id = doc_block.get("file_id", "manual")
    file_name = doc_block.get("file_name", "unknown")
    chunks = body.get("chunks", [])

    if not chunks:
        logger.warning("Empty chunks list received. Skipping message.")
        return True

    from haystack import Document

    haystack_docs = []
    for chunk in chunks:
        text = chunk.get("content") or chunk.get("text", "")
        doc = Document(
            content=text,
            meta={
                "file_id": file_id,
                "file_name": file_name,
                "chunk_index": chunk["chunk_index"],
                "page_number": chunk.get("page_number", 1)
            }
        )
        haystack_docs.append(doc)

    try:
        pipeline.run({"splade_processor": {"documents": haystack_docs}})
        return True
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return False

def main():
    global graceful_exit

    if not config.AWS_SQS_STAGE_2_URL:
        logger.error("AWS_SQS_STAGE_2_URL must be configured.")
        sys.exit(1)

    logger.info("Initializing SQS client...")
    try:
        sqs_client = get_sqs_client()
    except Exception as e:
        logger.error(f"Failed to initialize SQS client: {e}")
        sys.exit(1)

    pipeline = None
    logger.info("Starting Ephemeral Indexer Worker Loop...")

    while not graceful_exit:
        try:
            logger.info("Polling SQS Stage 2 queue...")
            response = sqs_client.receive_message(
                QueueUrl=config.AWS_SQS_STAGE_2_URL,
                MaxNumberOfMessages=config.FETCH_BATCH_SIZE,
                WaitTimeSeconds=config.POLL_WAIT_TIME_SECONDS
            )

            messages = response.get("Messages", [])
            if not messages:
                if config.CONTINUOUS_POLL:
                    logger.info(f"No messages in Stage 2 queue. Sleeping {config.POLL_SLEEP_INTERVAL_SECONDS} seconds...")
                    time.sleep(config.POLL_SLEEP_INTERVAL_SECONDS)
                    continue
                else:
                    logger.info("No messages in Stage 2 queue. Exiting (Queue drained cleanly).")
                    break

            if pipeline is None:
                logger.info("Building Haystack pipeline (lazy loading)...")
                from fastembed import SparseTextEmbedding
                model = SparseTextEmbedding(model_name=config.SPLADE_MODEL_NAME)
                pipeline = build_haystack_pipeline(splade_model=model)
                logger.info("SPLADE model and Haystack pipeline are fully loaded and ready.")

            for msg in messages:
                if graceful_exit:
                    logger.info("Graceful exit triggered. Stopping batch processing...")
                    break

                receipt_handle = msg["ReceiptHandle"]
                logger.info(f"Processing message ID: {msg['MessageId']}")
                if process_sqs_message(msg["Body"], pipeline):
                    sqs_client.delete_message(QueueUrl=config.AWS_SQS_STAGE_2_URL, ReceiptHandle=receipt_handle)

        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {e}")
            time.sleep(config.POLL_SLEEP_INTERVAL_SECONDS)

    logger.info("Indexer worker terminated cleanly.")

if __name__ == "__main__":
    main()
