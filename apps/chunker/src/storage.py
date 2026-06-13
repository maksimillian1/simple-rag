import os
import logging

logger = logging.getLogger("chunker")

def get_s3_client():
    """
    Construct S3 client using environment configurations.
    """
    import boto3
    from . import config
    
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

def validate_object_size(bucket_name: str, object_key: str, object_size: int | None, max_size: int) -> bool:
    if bucket_name == "local":
        try:
            if os.path.exists(object_key):
                object_size = os.path.getsize(object_key)
        except Exception as e:
            logger.warning(f"Failed to resolve file size for local path {object_key}: {e}")

    if object_size is not None and object_size > max_size:
        logger.warning(f"File too large ({object_size} bytes). Aborting download path. Limit is {max_size} bytes.")
        return False
    return True

def download_file_to_local(s3_client, bucket_name: str, object_key: str, temp_file_path: str) -> None:
    if bucket_name != "local":
        logger.info(f"Downloading s3://{bucket_name}/{object_key} to local temporary storage...")
        s3_client.download_file(bucket_name, object_key, temp_file_path)
