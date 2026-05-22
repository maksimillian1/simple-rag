resource "aws_sqs_queue" "rag_queue" {
  name = var.queue_name

  # Enable Long Polling
  receive_wait_time_seconds = 20

  tags = var.tags
}

# Allow S3 bucket to send messages to the SQS queue
resource "aws_sqs_queue_policy" "rag_queue_policy" {
  queue_url = aws_sqs_queue.rag_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.rag_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_s3_bucket.rag_bucket.arn
          }
        }
      }
    ]
  })
}
