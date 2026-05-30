resource "random_id" "bucket_suffix" {
  byte_length = 6
}

locals {
  bucket_name = "${var.resource_prefix}-raw-docs-${random_id.bucket_suffix.hex}"
}

# Dead-Letter Queue for Stage 1 Parsing Queue
resource "aws_sqs_queue" "stage_1_dlq" {
  name                      = "${var.resource_prefix}-stage-1-parsing-dlq"
  message_retention_seconds = 1209600 # 14 days
}

# SQS Queue for Stage 1 Parsing (S3 notifications target)
resource "aws_sqs_queue" "stage_1_queue" {
  name                      = "${var.resource_prefix}-stage-1-parsing"
  receive_wait_time_seconds = 20 # Enable Long Polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.stage_1_dlq.arn
    maxReceiveCount     = 3
  })
}

# Dead-Letter Queue for Stage 2 Indexing Queue
resource "aws_sqs_queue" "stage_2_dlq" {
  name                      = "${var.resource_prefix}-stage-2-indexing-dlq"
  message_retention_seconds = 1209600 # 14 days
}

# SQS Queue for Stage 2 Indexing (parsed chunks to indexer)
resource "aws_sqs_queue" "stage_2_queue" {
  name                      = "${var.resource_prefix}-stage-2-indexing"
  receive_wait_time_seconds = 20 # Enable Long Polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.stage_2_dlq.arn
    maxReceiveCount     = 3
  })
}

# S3 Bucket for Raw Documents Ingestion
resource "aws_s3_bucket" "raw_bucket" {
  bucket        = local.bucket_name
  force_destroy = true # Convenient for test environment cleanup
}

# Ensure the S3 bucket is completely private
resource "aws_s3_bucket_public_access_block" "raw_bucket_public_access" {
  bucket = aws_s3_bucket.raw_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Allow S3 bucket to publish notifications to the Stage 1 SQS Queue
resource "aws_sqs_queue_policy" "stage_1_queue_policy" {
  queue_url = aws_sqs_queue.stage_1_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.stage_1_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_s3_bucket.raw_bucket.arn
          }
        }
      }
    ]
  })
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
