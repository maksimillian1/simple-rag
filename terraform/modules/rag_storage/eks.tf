module "eks" {
  count  = var.is_local_test ? 0 : 1
  source = "./modules/eks"

  cluster_name    = var.cluster_name
  vpc_id          = one(module.vpc[*].vpc_id)
  private_subnets = one(module.vpc[*].private_subnets)
  tags            = local.merged_tags
}
