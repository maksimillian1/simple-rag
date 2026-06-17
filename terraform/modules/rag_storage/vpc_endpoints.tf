module "vpc_endpoints" {
  count   = var.is_local_test ? 0 : 1
  source  = "terraform-aws-modules/vpc/aws//modules/vpc-endpoints"
  version = "~> 5.0"

  vpc_id = module.vpc[0].vpc_id

  security_group_ids = [aws_security_group.bedrock_endpoint_sg[0].id]

  endpoints = {
    bedrock_runtime = {
      service             = "bedrock-runtime"
      private_dns_enabled = true
      subnet_ids          = module.vpc[0].private_subnets
    },
    bedrock = {
      service             = "bedrock"
      private_dns_enabled = true
      subnet_ids          = module.vpc[0].private_subnets
    }
  }

  tags = local.merged_tags
}

resource "aws_security_group" "bedrock_endpoint_sg" {
  count       = var.is_local_test ? 0 : 1
  name        = "${var.resource_prefix}-bedrock-endpoint-sg"
  description = "Security Group for AWS Bedrock VPC Endpoints"
  vpc_id      = module.vpc[0].vpc_id

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
