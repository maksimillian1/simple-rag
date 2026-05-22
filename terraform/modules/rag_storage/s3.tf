resource "aws_s3_bucket" "rag_bucket" {
  bucket = var.bucket_name

  tags = var.tags
}

# Ensure the bucket is private
resource "aws_s3_bucket_public_access_block" "rag_bucket_public_access_block" {
  bucket = aws_s3_bucket.rag_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Configure S3 bucket notification to send to SQS
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.rag_bucket.id

  queue {
    queue_arn = aws_sqs_queue.rag_queue.arn
    events    = ["s3:ObjectCreated:*"]
  }

  # Ensure the SQS policy is attached before trying to create the notification
  depends_on = [aws_sqs_queue_policy.rag_queue_policy]
}
