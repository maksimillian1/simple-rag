variable "aws_region" {
  description = "AWS region to deploy resources to"
  type        = string
  default     = "eu-central-1"
}

variable "resource_prefix" {
  description = "Prefix for resources to guarantee uniqueness and project grouping"
  type        = string
  default     = "simple-rag"
}

variable "is_local_test" {
  description = "Whether it is a local test run where AWS resources should not be provisioned."
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for the private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24", "10.0.12.0/24"]
}

variable "single_nat_gateway" {
  description = "If true, provision a single shared NAT Gateway for cost-efficiency"
  type        = bool
  default     = true
}
