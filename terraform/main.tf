locals {
  cluster_name = "${var.resource_prefix}-cluster"
  tags = {
    app         = "simple-rag"
    environment = var.is_local_test ? "local-test" : "dev"
    managed-by  = "terraform"
  }
}

module "rag_storage" {
  source = "./modules/rag_storage"

  resource_prefix      = var.resource_prefix
  is_local_test        = var.is_local_test
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway   = var.single_nat_gateway
  cluster_name         = local.cluster_name

  tags = local.tags
}

output "rag_s3_bucket" {
  value = module.rag_storage.s3_bucket_name
}

output "rag_s3_bucket_arn" {
  value = module.rag_storage.s3_bucket_arn
}

output "rag_sqs_queue" {
  value = module.rag_storage.sqs_stage_1_queue_url
}

output "rag_sqs_stage_1_queue" {
  value = module.rag_storage.sqs_stage_1_queue_url
}

output "rag_sqs_stage_1_queue_arn" {
  value = module.rag_storage.sqs_stage_1_queue_arn
}

output "rag_sqs_stage_2_queue" {
  value = module.rag_storage.sqs_stage_2_queue_url
}

output "rag_sqs_stage_2_queue_arn" {
  value = module.rag_storage.sqs_stage_2_queue_arn
}

output "vpc_id" {
  value = module.rag_storage.vpc_id
}

output "private_subnets" {
  value = module.rag_storage.private_subnets
}

output "public_subnets" {
  value = module.rag_storage.public_subnets
}

output "eks_cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.rag_storage.eks_cluster_endpoint
}

output "eks_oidc_provider_url" {
  description = "OIDC Issuer URL of EKS cluster"
  value       = module.rag_storage.eks_oidc_provider_url
}

output "eks_cluster_security_group_id" {
  description = "Cluster-wide security group ID of EKS cluster"
  value       = module.rag_storage.eks_cluster_security_group_id
}

output "eks_karpenter_controller_role_arn" {
  description = "IAM Role ARN for Karpenter controller"
  value       = module.rag_storage.eks_karpenter_controller_role_arn
}
