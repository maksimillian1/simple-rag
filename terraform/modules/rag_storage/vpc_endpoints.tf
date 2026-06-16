module "vpc_endpoints" {
  source  = "terraform-aws-modules/vpc/aws//modules/vpc-endpoints"
  version = "~> 5.0"

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

  tags = local.merged_tags
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

  tags = local.merged_tags
}
