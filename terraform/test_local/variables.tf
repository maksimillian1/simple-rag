variable "aws_region" {
  description = "AWS region to deploy resources to"
  type        = string
  default     = "eu-central-1"
}

variable "resource_prefix" {
  description = "Prefix for resources to guarantee uniqueness and project grouping"
  type        = string
  default     = "simple-rag-test"
}
