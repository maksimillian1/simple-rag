data "aws_availability_zones" "available" {
  state = "available"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"

  name = "${var.resource_prefix}-vpc"
  cidr = var.vpc_cidr

  azs             = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets = var.private_subnet_cidrs
  public_subnets  = var.public_subnet_cidrs

  enable_nat_gateway = !var.create_nat_instance
  single_nat_gateway = var.single_nat_gateway

  enable_dns_hostnames = true
  enable_dns_support   = true

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
    "karpenter.sh/discovery"          = var.cluster_name
  }

  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }

  tags = var.tags
}

module "vpc_endpoints" {
  source  = "terraform-aws-modules/vpc/aws//modules/vpc-endpoints"
  version = "~> 6.0"

  vpc_id = module.vpc.vpc_id

  security_group_ids = [aws_security_group.bedrock_endpoint_sg.id]

  endpoints = {
    bedrock_runtime = {
      service             = "bedrock-runtime"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
    },
    bedrock = {
      service             = "bedrock"
      private_dns_enabled = true
      subnet_ids          = module.vpc.private_subnets
    }
  }

  tags = var.tags
}

resource "aws_security_group" "bedrock_endpoint_sg" {
  name        = "${var.resource_prefix}-bedrock-endpoint-sg"
  description = "Security Group for AWS Bedrock VPC Endpoints"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}
