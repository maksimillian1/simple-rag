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
    value = var.karpenter_interruption_queue_name
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = var.karpenter_controller_role_arn
  }

  depends_on = [
    module.eks_core_nodes,
    helm_release.cilium,
    aws_eks_addon.aws_ebs_csi_driver,
    aws_eks_addon.pod_identity
  ]
  timeout = 600
}

resource "helm_release" "karpenter_resources" {
  name      = "karpenter-resources"
  chart     = "${path.module}/karpenter-resources"
  namespace = "karpenter"
  replace          = true
  cleanup_on_fail  = true

  set {
    name  = "clusterName"
    value = var.cluster_name
  }

  depends_on = [helm_release.karpenter]
  timeout    = 600
}
