data "aws_iam_policy_document" "pod_identity_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api_role" {
  name               = "rag-api-role"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "api_s3" {
  role       = aws_iam_role.api_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

resource "aws_eks_pod_identity_association" "api" {
  cluster_name    = var.cluster_name
  namespace       = "rag-api"
  service_account = "api-sa"
  role_arn        = aws_iam_role.api_role.arn
}

resource "aws_iam_role" "chunker_role" {
  name               = "rag-chunker-role"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "chunker_sqs" {
  role       = aws_iam_role.chunker_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSQSFullAccess"
}

resource "aws_eks_pod_identity_association" "chunker" {
  cluster_name    = var.cluster_name
  namespace       = "rag-jobs-private"
  service_account = "chunker-sa"
  role_arn        = aws_iam_role.chunker_role.arn
}
