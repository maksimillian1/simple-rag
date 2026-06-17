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

output "vpc_id" {
  description = "ID of the created VPC"
  value       = one(module.vpc[*].vpc_id)
}

output "private_subnets" {
  description = "List of IDs of private subnets"
  value       = one(module.vpc[*].private_subnets)
}

output "public_subnets" {
  description = "List of IDs of public subnets"
  value       = one(module.vpc[*].public_subnets)
}

output "eks_cluster_endpoint" {
  description = "EKS Cluster Endpoint URL"
  value       = one(module.eks[*].cluster_endpoint)
}

output "eks_oidc_provider_url" {
  description = "OIDC Provider URL for the EKS Cluster"
  value       = one(module.eks[*].oidc_provider_url)
}

output "eks_cluster_security_group_id" {
  description = "Security Group ID of the EKS Cluster"
  value       = one(module.eks[*].cluster_security_group_id)
}

output "eks_karpenter_controller_role_arn" {
  description = "IAM Role ARN for the Karpenter controller"
  value       = one(module.eks[*].karpenter_controller_role_arn)
}
