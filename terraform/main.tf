locals {
  cluster_name = "${var.resource_prefix}-cluster"
  tags = {
    app         = "simple-rag"
    environment = var.is_local_test ? "local-test" : "dev"
    managed-by  = "terraform"
  }
}

module "rag_core" {
  source = "./modules/01-rag-core"

  resource_prefix      = var.resource_prefix
  is_local_test        = var.is_local_test
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway   = var.single_nat_gateway
  cluster_name         = local.cluster_name

  tags = local.tags
}

data "aws_eks_cluster" "this" {
  count      = var.is_local_test ? 0 : 1
  name       = module.rag_core.cluster_name
  depends_on = [module.rag_core]
}

module "rag_k8s" {
  source = "./modules/02-rag-k8s"
  count  = var.is_local_test ? 0 : 1

  cluster_name                      = module.rag_core.cluster_name
  karpenter_node_role_arn           = module.rag_core.karpenter_node_role_arn
  karpenter_controller_role_arn     = module.rag_core.eks_karpenter_controller_role_arn
  karpenter_interruption_queue_name = module.rag_core.eks_karpenter_interruption_queue_name

  node_security_group_id            = module.rag_core.node_security_group_id
  cluster_primary_security_group_id = module.rag_core.cluster_primary_security_group_id
  private_subnets                   = module.rag_core.private_subnets

  cluster_endpoint     = data.aws_eks_cluster.this[0].endpoint
  cluster_auth_base64  = data.aws_eks_cluster.this[0].certificate_authority[0].data
  cluster_service_cidr = data.aws_eks_cluster.this[0].kubernetes_network_config[0].service_ipv4_cidr

  cluster_oidc_provider_arn = module.rag_core.eks_oidc_provider_arn
  cluster_oidc_provider     = module.rag_core.eks_oidc_provider

  tags = local.tags
  
  github_token = var.github_token

  depends_on = [module.rag_core]
}
