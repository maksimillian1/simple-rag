# Dead-Letter Queue for Stage 1 Parsing Queue
resource "aws_sqs_queue" "stage_1_dlq" {
  name                      = "${var.resource_prefix}-stage-1-parsing-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = local.merged_tags
}

# SQS Queue for Stage 1 Parsing (S3 notifications target)
resource "aws_sqs_queue" "stage_1_queue" {
  name                      = "${var.resource_prefix}-stage-1-parsing"
  receive_wait_time_seconds = 20 # Enable Long Polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.stage_1_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.merged_tags
}

# Dead-Letter Queue for Stage 2 Indexing Queue
resource "aws_sqs_queue" "stage_2_dlq" {
  name                      = "${var.resource_prefix}-stage-2-indexing-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = local.merged_tags
}

# SQS Queue for Stage 2 Indexing (parsed chunks to indexer)
resource "aws_sqs_queue" "stage_2_queue" {
  name                      = "${var.resource_prefix}-stage-2-indexing"
  receive_wait_time_seconds = 20 # Enable Long Polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.stage_2_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.merged_tags
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
