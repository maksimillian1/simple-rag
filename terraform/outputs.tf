output "rag_s3_bucket" {
  value = module.rag_core.s3_bucket_name
}

output "rag_s3_bucket_arn" {
  value = module.rag_core.s3_bucket_arn
}

output "rag_sqs_queue" {
  value = module.rag_core.sqs_stage_1_queue_url
}

output "rag_sqs_stage_1_queue" {
  value = module.rag_core.sqs_stage_1_queue_url
}

output "rag_sqs_stage_1_queue_arn" {
  value = module.rag_core.sqs_stage_1_queue_arn
}

output "rag_sqs_stage_2_queue" {
  value = module.rag_core.sqs_stage_2_queue_url
}

output "rag_sqs_stage_2_queue_arn" {
  value = module.rag_core.sqs_stage_2_queue_arn
}

output "qdrant_ebs_volume_id" {
  description = "The AWS EBS Volume ID provisioned for Qdrant"
  value       = module.rag_core.qdrant_ebs_volume_id
}

output "vpc_id" {
  value = module.rag_core.vpc_id
}

output "private_subnets" {
  value = module.rag_core.private_subnets
}

output "public_subnets" {
  value = module.rag_core.public_subnets
}

output "eks_cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.rag_core.eks_cluster_endpoint
}

output "eks_oidc_provider_url" {
  description = "OIDC Issuer URL of EKS cluster"
  value       = module.rag_core.eks_oidc_provider_url
}

output "eks_cluster_security_group_id" {
  description = "Cluster-wide security group ID of EKS cluster"
  value       = module.rag_core.eks_cluster_security_group_id
}

output "eks_karpenter_controller_role_arn" {
  description = "IAM Role ARN for Karpenter controller"
  value       = module.rag_core.eks_karpenter_controller_role_arn
}
