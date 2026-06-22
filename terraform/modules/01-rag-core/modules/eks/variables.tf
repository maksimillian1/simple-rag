variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.36"
}

variable "resource_prefix" {
  description = "Prefix for resources"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the public subnets"
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for the private subnets"
  type        = list(string)
}

variable "tags" {
  description = "Map of tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "create_nat_instance" {
  description = "If true, provisions an fck-nat EC2 instance. If false, provisions a managed AWS NAT Gateway."
  type        = bool
}

variable "single_nat_gateway" {
  description = "If true, provision a single shared NAT Gateway for cost-efficiency"
  type        = bool
}
