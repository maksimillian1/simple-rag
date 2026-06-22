resource "random_id" "bucket_suffix" {
  byte_length = 6
}

locals {
  bucket_name = "${var.resource_prefix}-raw-docs-${random_id.bucket_suffix.hex}"
  default_tags = {
    app        = "simple-rag"
    managed-by = "terraform"
  }
  merged_tags = merge(local.default_tags, var.tags)
}

# S3 Bucket for Raw Documents Ingestion
resource "aws_s3_bucket" "raw_bucket" {
  bucket        = local.bucket_name
  force_destroy = true # Convenient for test environment cleanup

  tags = local.merged_tags
}

# Ensure the S3 bucket is completely private
resource "aws_s3_bucket_public_access_block" "raw_bucket_public_access" {
  bucket = aws_s3_bucket.raw_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Configure S3 bucket notification to send to Stage 1 SQS Queue on upload
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.raw_bucket.id

  queue {
    queue_arn = aws_sqs_queue.stage_1_queue.arn
    events    = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_sqs_queue_policy.stage_1_queue_policy]
}
