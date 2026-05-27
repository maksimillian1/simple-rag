import os
import sys
import json
import uuid
import signal
import logging
import requests
import boto3
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams

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
    sqs_endpoint = os.getenv("AWS_ENDPOINT_URL")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    # Fallback to local mock credentials if endpoints are defined
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if sqs_endpoint and not aws_access_key:
        aws_access_key = "mock"
        aws_secret_key = "mock"

    return boto3.client(
        "sqs",
        region_name=region,
        endpoint_url=sqs_endpoint,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key
    )

def generate_uuid5(file_name: str, chunk_index: int) -> str:
    """
    Generates a completely deterministic UUIDv5 Point ID for Qdrant.
    This guarantees that Spot evictions and retries are idempotent.
    """
    namespace = uuid.uuid5(uuid.NAMESPACE_DNS, "simple-rag.example.com")
    # Using format file_name_index
    unique_key = f"{file_name}_{chunk_index}"
    return str(uuid.uuid5(namespace, unique_key))

def main():
    global graceful_exit

    # Configurations
    queue_url = os.getenv("AWS_SQS_STAGE_2_URL")
    tei_endpoint = os.getenv("TEI_ENDPOINT", "http://localhost:8080")
    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6334"))
    collection_name = os.getenv("COLLECTION_NAME", "demo_collection")

    if not queue_url:
        logger.error("AWS_SQS_STAGE_2_URL must be configured.")
        sys.exit(1)

    logger.info("Initializing SQS client...")
    try:
        sqs_client = get_sqs_client()
    except Exception as e:
        logger.error(f"Failed to initialize SQS client: {e}")
        sys.exit(1)

    logger.info(f"Connecting to Qdrant via gRPC at {qdrant_host}:{qdrant_port}...")
    try:
        qdrant_client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            prefer_grpc=True
        )
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant client: {e}")
        sys.exit(1)

    logger.info("Starting Ephemeral Indexer Worker Loop...")

    while not graceful_exit:
        try:
            # Poll SQS with long polling (10 seconds)
            logger.info("Polling SQS Stage 2 queue...")
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10  # Long poll
            )

            messages = response.get("Messages", [])
            if not messages:
                continuous_poll = os.getenv("CONTINUOUS_POLL", "false").lower() == "true"
                if continuous_poll:
                    logger.info("No messages in Stage 2 queue. Sleeping 5 seconds for continuous polling...")
                    import time
                    time.sleep(5)
                    continue
                else:
                    logger.info("No messages in Stage 2 queue. Exiting (Queue drained cleanly).")
                    break

            message = messages[0]
            receipt_handle = message["ReceiptHandle"]
            body_str = message["Body"]

            logger.info(f"Processing message ID: {message['MessageId']}")

            try:
                body = json.loads(body_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON body from message: {e}")
                sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                continue

            file_name = body.get("file_name")
            metadata = body.get("metadata", {})
            chunks = body.get("chunks", [])

            if not file_name or not chunks:
                logger.error(f"Message payload is missing required fields (file_name or chunks): {body_str}")
                sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                continue

            logger.info(f"Batch Vectorizing {len(chunks)} chunks for: {file_name}")

            # Call TEI container to generate embeddings in one batch
            tei_url = f"{tei_endpoint}/embed"
            chunk_texts = [chunk["text"] for chunk in chunks]

            try:
                logger.info(f"Calling TEI at {tei_url} for batch embedding generation...")
                embed_response = requests.post(
                    tei_url,
                    json={"inputs": chunk_texts},
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                if embed_response.status_code != 200:
                    logger.error(f"TEI returned error code {embed_response.status_code}: {embed_response.text}")
                    continue

                embeddings = embed_response.json()

                # Verify embeddings format (should be list of lists of floats)
                if not isinstance(embeddings, list) or len(embeddings) != len(chunks):
                    logger.error(f"Unexpected response format from TEI: received {type(embeddings)} with length {len(embeddings) if isinstance(embeddings, list) else 'N/A'}")
                    continue

            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to connect to TEI container: {e}")
                # Retry on next poll
                continue

            # Ensure Qdrant Collection exists before upserting
            try:
                if not qdrant_client.collection_exists(collection_name):
                    logger.info(f"Collection '{collection_name}' not found. Creating collection with dimension 384 and Cosine distance...")
                    qdrant_client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(
                            size=384,  # bge-small-en-v1.5 output dimension
                            distance=Distance.COSINE
                        )
                    )
            except Exception as e:
                logger.error(f"Failed to verify/create Qdrant collection: {e}")
                continue

            # Build Qdrant points with deterministic Point IDs (UUID5) for idempotency
            points = []
            for i, chunk in enumerate(chunks):
                chunk_index = chunk["chunk_index"]
                text = chunk["text"]
                vector = embeddings[i]

                point_id = generate_uuid5(file_name, chunk_index)

                # Merge chunk text and parent metadata into Qdrant payload
                payload = {
                    "text": text,
                    "chunk_index": chunk_index,
                    "file_name": file_name,
                    **metadata
                }

                points.append(PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload
                ))

            # gRPC upsert to Qdrant
            try:
                logger.info(f"Upserting {len(points)} points to Qdrant collection '{collection_name}'...")
                qdrant_client.upsert(
                    collection_name=collection_name,
                    points=points,
                    wait=True
                )
                logger.info("Qdrant upsert completed successfully.")
            except Exception as e:
                logger.error(f"Failed to upsert points to Qdrant: {e}")
                continue

            # Delete processed message from SQS Stage 2
            logger.info("Deleting message from SQS Stage 2 queue...")
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
            logger.info("SQS message deleted successfully.")

        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {e}")
            import time
            time.sleep(5)

    logger.info("Indexer worker terminated cleanly.")

if __name__ == "__main__":
    main()
