resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "7.0.0"
  namespace        = "argocd"
  create_namespace = true

  set {
    name  = "server.service.type"
    value = "ClusterIP"
  }
}

resource "helm_release" "root_application" {
  name       = "argocd-root"
  chart      = "${path.module}/argocd-root"
  namespace  = "argocd"
  depends_on = [helm_release.argocd, helm_release.keda]

  set_sensitive {
    name  = "githubToken"
    value = var.github_token
  }

  set {
    name  = "sqsChunkerUrl"
    value = var.sqs_chunker_url
  }

  set {
    name  = "sqsIndexerUrl"
    value = var.sqs_indexer_url
  }

  set {
    name  = "componentNamespaces"
    value = "{${join(",", var.component_namespaces)}}"
  }
}
