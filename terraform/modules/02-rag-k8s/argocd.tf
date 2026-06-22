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

# resource "kubernetes_manifest" "root_application" {
#   depends_on = [helm_release.argocd]
#
#   manifest = {
#     apiVersion = "argoproj.io/v1alpha1"
#     kind       = "Application"
#     metadata = {
#       name      = "root-bootstrap"
#       namespace = "argocd"
#     }
#     spec = {
#       project = "default"
#       source = {
#         repoURL        = "https://github.com/maksimillian1/simple-rag.git"
#         targetRevision = "HEAD"
#         path           = "deploy"
#       }
#       destination = {
#         server    = "https://kubernetes.default.svc"
#         namespace = "argocd"
#       }
#       syncPolicy = {
#         automated = {
#           prune    = true
#           selfHeal = true
#         }
#       }
#     }
#   }
# }
