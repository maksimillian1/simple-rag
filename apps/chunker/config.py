import os

# AWS SQS Configuration
AWS_SQS_STAGE_1_URL = os.getenv("AWS_SQS_STAGE_1_URL")
AWS_SQS_STAGE_2_URL = os.getenv("AWS_SQS_STAGE_2_URL")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# Document Splitter Config
CHUNK_BY = os.getenv("CHUNK_BY", "word")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "20"))
CHUNK_RESPECT_SENTENCE = os.getenv("CHUNK_RESPECT_SENTENCE", "true").lower() == "true"

# Loop Configuration
CONTINUOUS_POLL = os.getenv("CONTINUOUS_POLL", "false").lower() == "true"
