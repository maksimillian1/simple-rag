output "s3_bucket_name" {
  description = "Name of the created S3 bucket"
  value       = aws_s3_bucket.rag_bucket.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the created S3 bucket"
  value       = aws_s3_bucket.rag_bucket.arn
}

output "sqs_queue_url" {
  description = "URL of the created SQS queue"
  value       = aws_sqs_queue.rag_queue.id
}

output "sqs_queue_arn" {
  description = "ARN of the created SQS queue"
  value       = aws_sqs_queue.rag_queue.arn
}
