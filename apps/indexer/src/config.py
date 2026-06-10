import os

# AWS SQS Configuration
AWS_SQS_STAGE_2_URL = os.getenv("AWS_SQS_STAGE_2_URL")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# TEI Configuration
EMBEDDING_MODEL_TEI_URL = os.getenv("EMBEDDING_MODEL_TEI_URL", "http://localhost:8080")
TEI_MAX_BATCH_SIZE = int(os.getenv("TEI_MAX_BATCH_SIZE", "32"))
TEI_EMBEDDING_MODEL = os.getenv("TEI_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# Qdrant Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6334"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "demo_collection")

# Worker Loop Configuration
FETCH_BATCH_SIZE = int(os.getenv("FETCH_BATCH_SIZE", "10"))
POLL_WAIT_TIME_SECONDS = int(os.getenv("POLL_WAIT_TIME_SECONDS", "10"))

# DEBUG
CONTINUOUS_POLL = os.getenv("CONTINUOUS_POLL", "false").lower() == "true"
POLL_SLEEP_INTERVAL_SECONDS = int(os.getenv("POLL_SLEEP_INTERVAL_SECONDS", "5"))
