import os

# AWS Configuration
AWS_SQS_STAGE_1_URL = os.getenv("AWS_SQS_STAGE_1_URL")
AWS_SQS_STAGE_2_URL = os.getenv("AWS_SQS_STAGE_2_URL")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-central-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# Document Splitter Config
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "300"))
DEFAULT_OVERLAP_TOKENS = int(os.getenv("DEFAULT_OVERLAP_TOKENS", "50"))
DEFAULT_LLAMA_MODEL = os.getenv("DEFAULT_LLAMA_MODEL", "unsloth/llama-3-8b-Instruct")

# Worker Loop & S3 Storage Config
MAX_ALLOWED_SIZE_BYTES = int(os.getenv("MAX_ALLOWED_SIZE_BYTES", "104857600"))  # 100MB
POLL_WAIT_TIME_SECONDS = int(os.getenv("POLL_WAIT_TIME_SECONDS", "10"))
ERROR_SLEEP_INTERVAL_SECONDS = int(os.getenv("ERROR_SLEEP_INTERVAL_SECONDS", "5"))

# Loop Configuration for Dev mode testing
POLL_SLEEP_INTERVAL_SECONDS = int(os.getenv("POLL_SLEEP_INTERVAL_SECONDS", "5"))
CONTINUOUS_POLL = os.getenv("CONTINUOUS_POLL", "false").lower() == "true"

# SQS Batch Config
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "40"))
