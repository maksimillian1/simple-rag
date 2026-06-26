resource "aws_eks_addon" "coredns" {
  depends_on = [module.eks_core_nodes]

  cluster_name = var.cluster_name
  addon_name   = "coredns"
  addon_version = "v1.14.3-eksbuild.3"
}

resource "aws_iam_role" "ebs_csi" {
  name = "${var.cluster_name}-ebs-csi"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = var.cluster_oidc_provider_arn
        }
        Condition = {
          StringEquals = {
            "${var.cluster_oidc_provider}:sub" = "system:serviceaccount:kube-system:ebs-csi-controller-sa"
            "${var.cluster_oidc_provider}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.ebs_csi.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_eks_addon" "aws_ebs_csi_driver" {
  depends_on = [module.eks_core_nodes]

  cluster_name             = var.cluster_name
  addon_name               = "aws-ebs-csi-driver"
  addon_version = "v1.62.0-eksbuild.1"

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  service_account_role_arn = aws_iam_role.ebs_csi.arn

  configuration_values = jsonencode({
    defaultStorageClass = {
      enabled = false
    }
  })
}

resource "aws_eks_addon" "pod_identity" {
  cluster_name = var.cluster_name
  addon_name   = "eks-pod-identity"
}
