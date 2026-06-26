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
  depends_on = [helm_release.argocd]
}

resource "kubernetes_secret" "git_repository_creds" {
  metadata {
    name      = "git-repository-creds"
    namespace = "argocd"
    labels = {
      "argocd.argoproj.io/secret-type" = "repository"
    }
  }

  data = {
    type     = "git"
    url      = "https://github.com/maksimillian1/simple-rag.git"
    username = "argo"
    password = var.github_token
  }

  depends_on = [helm_release.argocd]
}
