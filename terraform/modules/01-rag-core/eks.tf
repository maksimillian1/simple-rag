module "eks" {
  count  = var.is_local_test ? 0 : 1
  source = "./modules/eks"

  cluster_name         = var.cluster_name
  resource_prefix      = var.resource_prefix
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  create_nat_instance  = var.create_nat_instance
  single_nat_gateway   = var.single_nat_gateway
  tags                 = local.merged_tags
}
