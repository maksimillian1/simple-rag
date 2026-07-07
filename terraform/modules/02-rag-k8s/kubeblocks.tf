resource "null_resource" "kubeblocks_crds" {
  provisioner "local-exec" {
    command = "kubectl apply --server-side -f https://github.com/apecloud/kubeblocks/releases/download/v1.0.2/kubeblocks_crds.yaml"
  }

  depends_on = [
    module.eks_core_nodes
  ]
}

resource "helm_release" "kubeblocks" {
  name             = "kubeblocks"
  repository       = "https://apecloud.github.io/helm-charts"
  chart            = "kubeblocks"
  version          = "1.0.2"
  namespace        = "kb-system"
  create_namespace = true

  depends_on = [
    module.eks_core_nodes,
    helm_release.cilium,
    null_resource.kubeblocks_crds
  ]
}

resource "helm_release" "kubeblocks_addon_qdrant" {
  name             = "qdrant"
  repository       = "https://apecloud.github.io/helm-charts"
  chart            = "qdrant"
  namespace        = "kb-system"

  depends_on = [
    helm_release.kubeblocks
  ]
}

