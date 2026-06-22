module "eks_core_nodes" {
  source  = "terraform-aws-modules/eks/aws//modules/eks-managed-node-group"
  version = "~> 21.0"

  name            = "core-on-demand"
  cluster_name           = var.cluster_name
  cluster_endpoint       = var.cluster_endpoint
  cluster_auth_base64    = var.cluster_auth_base64
  cluster_service_cidr   = var.cluster_service_cidr

  subnet_ids                        = var.private_subnets
  cluster_primary_security_group_id = var.cluster_primary_security_group_id
  vpc_security_group_ids            = [var.node_security_group_id]

  instance_types = ["t3.medium", "t3.large"]
  min_size       = 2
  max_size       = 3
  desired_size   = 2
  capacity_type  = "ON_DEMAND"
  
  enable_bootstrap_user_data = true
  use_custom_launch_template = true
  ami_type                   = "AL2023_x86_64_STANDARD"

  taints = {
    cilium = {
      key    = "node.cilium.io/agent-not-ready"
      value  = "true"
      effect = "NO_EXECUTE"
    }
  }

  labels = {
    "node.kubernetes.io/cni-welcome" = "cilium"
  }

  iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }
}
