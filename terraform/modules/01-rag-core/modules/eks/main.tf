module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = var.cluster_name
  kubernetes_version = var.cluster_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
  endpoint_private_access = true
  endpoint_public_access  = true

  enable_irsa = true

  enable_cluster_creator_admin_permissions = true

  node_security_group_tags = {
    "karpenter.sh/discovery" = var.cluster_name
  }

  node_security_group_additional_rules = var.create_nat_instance ? {
    ingress_fck_nat = {
      description              = "Allow inbound traffic from fck-nat instance for debugging"
      protocol                 = "-1"
      from_port                = 0
      to_port                  = 0
      type                     = "ingress"
      source_security_group_id = module.fck_nat[0].security_group_id
    }
  } : {}

  fargate_profiles = {
    karpenter = {
      selectors = [
        {
          namespace = "karpenter"
        }
      ]
      subnet_ids = module.vpc.private_subnets
    }
  }
}
