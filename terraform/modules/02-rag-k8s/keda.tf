resource "helm_release" "keda" {
  name             = "keda"
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  version          = "2.14.2"
  namespace        = "keda"
  create_namespace = true

  set {
    name  = "crds.install"
    value = "true"
  }

  depends_on = [
    module.eks_core_nodes,
    helm_release.cilium,
    aws_eks_pod_identity_association.keda,
    aws_eks_addon.pod_identity
  ]
}

resource "aws_iam_role" "keda_role" {
  name               = "rag-keda-role"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "keda_sqs" {
  role       = aws_iam_role.keda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSQSReadOnlyAccess"
}

resource "aws_eks_pod_identity_association" "keda" {
  cluster_name    = var.cluster_name
  namespace       = "keda"
  service_account = "keda-operator"
  role_arn        = aws_iam_role.keda_role.arn
}
