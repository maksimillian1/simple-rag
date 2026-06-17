data "aws_availability_zones" "available" {
  count = var.is_local_test ? 0 : 1
  state = "available"
}

module "vpc" {
  count   = var.is_local_test ? 0 : 1
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.resource_prefix}-vpc"
  cidr = var.vpc_cidr

  azs             = slice(data.aws_availability_zones.available[0].names, 0, 3)
  private_subnets = var.private_subnet_cidrs
  public_subnets  = var.public_subnet_cidrs

  enable_nat_gateway     = false

  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = local.merged_tags
}
