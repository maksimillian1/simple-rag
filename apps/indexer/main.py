import sys
import json
import signal
import logging
import time
import boto3

import config
from vector import generate_point_id, compute_sparse_vector

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

    # Use environment variables if explicitly set, otherwise let boto3 resolve credentials natively.
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

def parse_sqs_message(body_str: str) -> tuple[str, str, list[dict]] or None:
    """
    Parses and validates the SQS message body.
    Returns (file_id, file_name, chunks) or None if invalid.
    """
    try:
        body = json.loads(body_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON body from message: {e}")
        return None

    # Support both new contracts.md structure and manual debug seeder format
    doc_block = body.get("document", {})
    file_id = doc_block.get("file_id")
    file_name = doc_block.get("file_name") or body.get("file_name")
    chunks = body.get("chunks", [])

    if not file_name or not chunks:
        logger.error(f"Message payload is missing required fields (file_name or chunks): {body_str}")
        return None

    if not file_id:
        file_id = f"doc_manual_{hash(file_name) & 0xffffffff:08x}"

    return file_id, file_name, chunks

def generate_embeddings(tei_endpoint: str, chunk_texts: list[str]) -> list[list[float]] or None:
    """
    Calls TEI container in batched requests to generate embeddings.
    Returns list of vector embeddings or None on failure.
    """
    import requests
    tei_url = f"{tei_endpoint}/embed"
    embeddings = []

    for i in range(0, len(chunk_texts), config.TEI_MAX_BATCH_SIZE):
        batch_texts = chunk_texts[i:i + config.TEI_MAX_BATCH_SIZE]
        try:
            logger.info(f"Calling TEI at {tei_url} for batch embedding generation (slice {i} to {i + len(batch_texts)})...")
            embed_response = requests.post(
                tei_url,
                json={"inputs": batch_texts},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if embed_response.status_code != 200:
                logger.error(f"TEI returned error code {embed_response.status_code}: {embed_response.text}")
                return None

            batch_embeddings = embed_response.json()

            # Verify embeddings format (should be list of lists of floats)
            if not isinstance(batch_embeddings, list) or len(batch_embeddings) != len(batch_texts):
                logger.error(f"Unexpected response format from TEI: received {type(batch_embeddings)}")
                return None

            embeddings.extend(batch_embeddings)

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to TEI container: {e}")
            return None

    return embeddings

def ensure_collection_exists(qdrant_client, collection_name: str) -> bool:
    """
    Verifies if Qdrant collection exists, creating it with dual named config if not.
    """
    try:
        if not qdrant_client.collection_exists(collection_name):
            logger.info(f"Collection '{collection_name}' not found. Creating collection with named dense/sparse vector configuration...")
            from qdrant_client.models import VectorParams, Distance, SparseVectorParams, SparseIndexParams
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=384,  # bge-small-en-v1.5 output dimension
                        distance=Distance.COSINE
                    )
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(
                            on_disk=True
                        )
                    )
                }
            )
        return True
    except Exception as e:
        logger.error(f"Failed to verify/create Qdrant collection: {e}")
        return False

def prepare_qdrant_points(file_id: str, file_name: str, chunks: list[dict], chunk_texts: list[str], embeddings: list[list[float]]) -> list:
    """
    Prepares point payloads including dense/sparse vector combinations.
    """
    from qdrant_client.models import PointStruct, SparseVector
    points = []
    
    for i, chunk in enumerate(chunks):
        chunk_index = chunk["chunk_index"]
        page_number = chunk.get("page_number", 1)
        text = chunk_texts[i]
        vector = embeddings[i]
        sparse_vector = compute_sparse_vector(text)

        point_id = generate_point_id(file_name, chunk_index)

        # Payload structure mapping strictly to contracts.md
        payload = {
            "file_id": file_id,
            "file_name": file_name,
            "chunk_index": chunk_index,
            "page_number": page_number,
            "text": text,
            "indexed_at": int(time.time())
        }

        points.append(PointStruct(
            id=point_id,
            vector={
                "dense": vector,
                "sparse": SparseVector(
                    indices=sparse_vector["indices"],
                    values=sparse_vector["values"]
                )
            },
            payload=payload
        ))

    return points

def process_message(message: dict, sqs_client, queue_url: str, qdrant_client):
    """
    Process a single SQS message: parses it, generates embeddings,
    verifies collection exists, upserts points to Qdrant, and deletes message on success.
    Returns the qdrant_client (initializing lazily if needed).
    """
    receipt_handle = message["ReceiptHandle"]
    body_str = message["Body"]

    logger.info(f"Processing message ID: {message['MessageId']}")

    parsed = parse_sqs_message(body_str)
    if parsed is None:
        # Delete invalid message to prevent infinite SQS retry loops of malformed payloads
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return qdrant_client

    file_id, file_name, chunks = parsed

    # Lazy initialize Qdrant Client on first message processing
    if qdrant_client is None:
        logger.info("Initializing Qdrant client (lazy loading)...")
        from qdrant_client import QdrantClient
        use_grpc = (config.QDRANT_PORT == 6334)
        logger.info(f"Connecting to Qdrant at {config.QDRANT_HOST}:{config.QDRANT_PORT} (grpc={use_grpc})...")
        try:
            qdrant_client = QdrantClient(
                host=config.QDRANT_HOST,
                port=config.QDRANT_PORT,
                prefer_grpc=use_grpc
            )
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant client: {e}")
            # Keep message in queue for retry
            return None

    # Extract raw text payloads
    chunk_texts = [chunk.get("content") or chunk.get("text", "") for chunk in chunks]

    # Batch Generate Embeddings
    embeddings = generate_embeddings(config.TEI_ENDPOINT, chunk_texts)
    if embeddings is None:
        # Keep message in queue for retry
        return qdrant_client

    # Ensure collection structure is present
    if not ensure_collection_exists(qdrant_client, config.COLLECTION_NAME):
        # Keep message in queue for retry
        return qdrant_client

    # Generate point objects matching schema constraints
    points = prepare_qdrant_points(file_id, file_name, chunks, chunk_texts, embeddings)

    # Upsert payload structures to vector store
    try:
        logger.info(f"Upserting {len(points)} points to Qdrant collection '{config.COLLECTION_NAME}'...")
        qdrant_client.upsert(
            collection_name=config.COLLECTION_NAME,
            points=points,
            wait=True
        )
        logger.info("Qdrant upsert completed successfully.")
    except Exception as e:
        logger.error(f"Failed to upsert points to Qdrant: {e}")
        # Keep message in queue for retry
        return qdrant_client

    # Complete lifecycle deletion in message broker
    logger.info("Deleting message from SQS Stage 2 queue...")
    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
    logger.info("SQS message deleted successfully.")

    return qdrant_client

def main():
    global graceful_exit

    # Validate Queue Config
    queue_url = config.AWS_SQS_STAGE_2_URL
    if not queue_url:
        logger.error("AWS_SQS_STAGE_2_URL must be configured.")
        sys.exit(1)

    logger.info("Initializing SQS client...")
    try:
        sqs_client = get_sqs_client()
    except Exception as e:
        logger.error(f"Failed to initialize SQS client: {e}")
        sys.exit(1)

    qdrant_client = None

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
                if config.CONTINUOUS_POLL:
                    logger.info("No messages in Stage 2 queue. Sleeping 5 seconds for continuous polling...")
                    time.sleep(5)
                    continue
                else:
                    logger.info("No messages in Stage 2 queue. Exiting (Queue drained cleanly).")
                    break

            # Process the received message
            qdrant_client = process_message(messages[0], sqs_client, queue_url, qdrant_client)

        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {e}")
            time.sleep(5)

    logger.info("Indexer worker terminated cleanly.")

if __name__ == "__main__":
    main()
