import sys
import json
import signal
import logging
import time
import boto3

import config
from vector import compute_sparse_vector

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("indexer")

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

def build_haystack_pipeline():
    """
    Builds the declarative Haystack 2.0 Ingestion Pipeline.
    Leverages TEIDocumentEmbedder and QdrantDocumentWriter natively.
    """
    from haystack import Pipeline
    from haystack.components.embedders import TEIDocumentEmbedder
    from haystack_integrations.components.writers.qdrant import QdrantDocumentWriter

    pipeline = Pipeline()

    # Step 1: Colocated TEI Sidecar for embedding generation
    pipeline.add_component("embedder", TEIDocumentEmbedder(
        url=config.TEI_ENDPOINT,
        model="BAAI/bge-small-en-v1.5"
    ))

    # Step 2: Native Qdrant Writer
    pipeline.add_component("writer", QdrantDocumentWriter(
        host=config.QDRANT_HOST,
        port=config.QDRANT_PORT,
        collection=config.COLLECTION_NAME,
        prefer_grpc=True
    ))

    pipeline.connect("embedder.documents", "writer.documents")
    return pipeline

def process_sqs_message(message_body: str, pipeline) -> bool:
    """
    Processes a single SQS message payload through the Haystack Ingestion Pipeline.
    Translates raw message chunks to Haystack Document objects with custom sparse embeddings.
    """
    try:
        body = json.loads(message_body)
    except Exception as e:
        logger.error(f"Failed to parse JSON body from message: {e}")
        return True # Delete invalid JSON to avoid infinite loops

    doc_block = body.get("document", {})
    file_id = doc_block.get("file_id", "manual")
    file_name = doc_block.get("file_name", "unknown")
    chunks = body.get("chunks", [])

    if not chunks:
        logger.warning("Empty chunks list received. Skipping message.")
        return True

    from haystack import Document

    # Map SQS chunks to native Haystack Documents
    haystack_docs = []
    for chunk in chunks:
        text = chunk.get("content") or chunk.get("text", "")
        
        # Calculate term frequency sparse vector representation
        sparse_res = compute_sparse_vector(text)

        doc = Document(
            content=text,
            meta={
                "file_id": file_id,
                "file_name": file_name,
                "chunk_index": chunk["chunk_index"],
                "page_number": chunk.get("page_number", 1)
            }
        )
        # Store sparse embedding so that the QdrantDocumentWriter can fetch it natively
        doc.sparse_embedding = sparse_res
        haystack_docs.append(doc)

    # Execute Haystack Pipeline (automatically batches, generates embeddings at TEI, and records to Qdrant)
    try:
        pipeline.run({"embedder": {"documents": haystack_docs}})
        return True
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return False # Keep in SQS queue for retry

def main():
    global graceful_exit

    # Validate Queue Config
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
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10  # Long poll
            )

            messages = response.get("Messages", [])
            if not messages:
                if config.CONTINUOUS_POLL:
                    logger.info("No messages in Stage 2 queue. Sleeping 5 seconds for continuous polling...")
                    time.sleep(5)
                    continue
                else:
                    logger.info("No messages in Stage 2 queue. Exiting (Queue drained cleanly).")
                    break

            msg = messages[0]
            receipt_handle = msg["ReceiptHandle"]

            # Lazily build declarative Haystack pipeline on first active message
            if pipeline is None:
                logger.info("Building Haystack pipeline (lazy loading)...")
                pipeline = build_haystack_pipeline()

            logger.info(f"Processing message ID: {msg['MessageId']}")
            if process_sqs_message(msg["Body"], pipeline):
                logger.info("Deleting message from SQS Stage 2 queue...")
                sqs_client.delete_message(QueueUrl=config.AWS_SQS_STAGE_2_URL, ReceiptHandle=receipt_handle)
                logger.info("SQS message deleted successfully.")

        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {e}")
            time.sleep(5)

    logger.info("Indexer worker terminated cleanly.")

if __name__ == "__main__":
    main()
