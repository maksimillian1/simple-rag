resource "aws_iam_policy" "aws_lbc_policy" {
  name        = "rag-aws-lbc-policy"
  description = "IAM Policy for AWS Load Balancer Controller"
  policy      = file("${path.module}/iam_policy_lbc.json")
}

resource "aws_iam_role" "aws_lbc_role" {
  name               = "rag-aws-lbc-role"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "aws_lbc_policy_attachment" {
  role       = aws_iam_role.aws_lbc_role.name
  policy_arn = aws_iam_policy.aws_lbc_policy.arn
}

resource "aws_eks_pod_identity_association" "aws_lbc" {
  cluster_name    = var.cluster_name
  namespace       = "kube-system"
  service_account = "aws-load-balancer-controller"
  role_arn        = aws_iam_role.aws_lbc_role.arn
}

