variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.31"
}

variable "vpc_id" {
  description = "VPC ID where EKS will be deployed"
  type        = string
}

variable "private_subnets" {
  description = "List of private subnet IDs for EKS"
  type        = list(string)
}

variable "tags" {
  description = "Map of tags to apply to all resources"
  type        = map(string)
  default     = {}
}
