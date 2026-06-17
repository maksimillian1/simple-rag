output "cluster_endpoint" {
  description = "EKS Cluster Endpoint URL"
  value       = module.eks.cluster_endpoint
}

output "oidc_provider_url" {
  description = "OIDC Provider URL for the EKS Cluster"
  value       = module.eks.cluster_oidc_issuer_url
}

output "cluster_security_group_id" {
  description = "Security Group ID of the EKS Cluster"
  value       = module.eks.cluster_security_group_id
}

output "karpenter_controller_role_arn" {
  description = "IAM Role ARN for the Karpenter controller"
  value       = aws_iam_role.karpenter_controller.arn
}
