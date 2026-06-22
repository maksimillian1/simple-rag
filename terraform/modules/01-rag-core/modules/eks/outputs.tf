output "cluster_endpoint" {
  description = "EKS Cluster Endpoint URL"
  value       = module.eks.cluster_endpoint
}

output "oidc_provider_url" {
  description = "OIDC Provider URL for the EKS Cluster"
  value       = module.eks.cluster_oidc_issuer_url
}

output "oidc_provider_arn" {
  description = "OIDC Provider ARN for the EKS Cluster"
  value       = module.eks.oidc_provider_arn
}

output "oidc_provider" {
  description = "OIDC Provider for the EKS Cluster (without https://)"
  value       = module.eks.oidc_provider
}

output "cluster_security_group_id" {
  description = "Security Group ID of the EKS Cluster"
  value       = module.eks.cluster_security_group_id
}

output "cluster_primary_security_group_id" {
  description = "Primary Security Group ID of the EKS Cluster"
  value       = module.eks.cluster_primary_security_group_id
}

output "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  value       = module.eks.cluster_version
}

output "node_security_group_id" {
  description = "Node Security Group ID of the EKS Cluster"
  value       = module.eks.node_security_group_id
}

output "karpenter_controller_role_arn" {
  description = "IAM Role ARN for the Karpenter controller"
  value       = aws_iam_role.karpenter_controller.arn
}

output "cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data required to communicate with the cluster"
  value       = module.eks.cluster_certificate_authority_data
}

output "karpenter_interruption_queue_name" {
  description = "Name of the Karpenter interruption queue"
  value       = aws_sqs_queue.karpenter_interruption.name
}

output "karpenter_node_role_arn" {
  description = "IAM Role ARN for the Karpenter node"
  value       = aws_iam_role.karpenter_node.arn
}

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "private_subnets" {
  description = "List of IDs of private subnets"
  value       = module.vpc.private_subnets
}

output "public_subnets" {
  description = "List of IDs of public subnets"
  value       = module.vpc.public_subnets
}

output "qdrant_ebs_volume_id" {
  description = "ID of the 150GB gp3 EBS volume provisioned for Qdrant"
  value       = aws_ebs_volume.qdrant.id
}

output "update_kubeconfig" {
  description = "Command to launch to use kubectl"
  value       = "aws eks update-kubeconfig --name ${var.cluster_name} --kubeconfig ~/.kube/config"
}
