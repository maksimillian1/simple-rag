variable "cluster_endpoint" {
  description = "EKS Cluster Endpoint"
  type        = string
}

variable "cluster_auth_base64" {
  description = "EKS Cluster Auth Base64"
  type        = string
}

variable "cluster_service_cidr" {
  description = "EKS Cluster Service CIDR"
  type        = string
}

variable "cluster_oidc_provider_arn" {
  description = "EKS Cluster OIDC Provider ARN"
  type        = string
}

variable "cluster_oidc_provider" {
  description = "EKS Cluster OIDC Provider (without https://)"
  type        = string
}

variable "cluster_name" {
  description = "EKS Cluster Name"
  type        = string
}

variable "karpenter_node_role_arn" {
  description = "Karpenter node role arn"
  type        = string
}

variable "karpenter_controller_role_arn" {
  description = "Karpenter controller role arn"
  type        = string
}

variable "karpenter_interruption_queue_name" {
  description = "Karpenter interruption queue name"
  type        = string
}

variable "node_security_group_id" {
  description = "Node security group ID from the cluster"
  type        = string
}

variable "cluster_primary_security_group_id" {
  description = "Cluster primary security group ID"
  type        = string
}

variable "private_subnets" {
  description = "List of private subnet IDs"
  type        = list(string)
}

variable "tags" {
  description = "Map of tags to apply to all resources"
  type        = map(string)
  default     = {}
}
