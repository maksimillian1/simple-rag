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

  depends_on = [module.eks_core_nodes, helm_release.cilium]
}

resource "kubernetes_secret" "argocd_cluster" {
  metadata {
    name      = "eks-cluster-${var.cluster_name}"
    namespace = "argocd"

    labels = {
      "argocd.argoproj.io/secret-type" = "cluster"
    }
  }

  type = "Opaque"

  data = {
    name   = var.cluster_name
    server = var.cluster_endpoint
    config = jsonencode({
      awsAuthConfig = {
        clusterName = var.cluster_name
      }
      tlsClientConfig = {
        insecure = false
        caData   = var.cluster_auth_base64
      }
    })
    values = jsonencode({
      vpc_id = var.vpc_id
    })
  }
}

resource "helm_release" "root_application" {
  name       = "argocd-root"
  chart      = "${path.module}/argocd-root"
  namespace  = "argocd"
  depends_on = [helm_release.argocd, helm_release.keda]
  timeout    = 600

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

