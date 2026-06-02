output "aws_region" {
  description = "AWS Region of deployment"
  value       = var.aws_region
}

output "s3_bucket_name" {
  description = "S3 Bucket Name for Raw Document Ingestion"
  value       = aws_s3_bucket.raw_bucket.id
}

output "s3_bucket_arn" {
  description = "S3 Bucket ARN"
  value       = aws_s3_bucket.raw_bucket.arn
}

output "sqs_stage_1_queue_url" {
  description = "URL of SQS Queue for Stage 1 (Parsing/Chunking)"
  value       = aws_sqs_queue.stage_1_queue.id
}

output "sqs_stage_1_queue_arn" {
  description = "ARN of SQS Queue for Stage 1 (Parsing/Chunking)"
  value       = aws_sqs_queue.stage_1_queue.arn
}

output "sqs_stage_2_queue_url" {
  description = "URL of SQS Queue for Stage 2 (Indexing)"
  value       = aws_sqs_queue.stage_2_queue.id
}

output "sqs_stage_2_queue_arn" {
  description = "ARN of SQS Queue for Stage 2 (Indexing)"
  value       = aws_sqs_queue.stage_2_queue.arn
}
