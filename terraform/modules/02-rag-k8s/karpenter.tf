resource "helm_release" "karpenter" {
  namespace        = "karpenter"
  create_namespace = true
  name             = "karpenter"
  repository       = "oci://public.ecr.aws/karpenter"
  chart            = "karpenter"
  replace          = true
  cleanup_on_fail  = true
  version          = "1.13.0"

  set {
    name  = "controller.resources.requests.cpu"
    value = "300m"
  }

  set {
    name  = "controller.resources.requests.memory"
    value = "512Mi"
  }

  set {
    name  = "settings.clusterName"
    value = var.cluster_name
  }

  set {
    name  = "settings.interruptionQueue"
    value = aws_sqs_queue.karpenter_interruption.name
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = aws_iam_role.karpenter_controller.arn
  }

  depends_on = [
    module.eks_core_nodes,
    helm_release.cilium,
    aws_eks_addon.aws_ebs_csi_driver,
    aws_eks_addon.pod_identity
  ]
  timeout = 600
}

