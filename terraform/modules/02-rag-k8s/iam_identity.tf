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

resource "aws_iam_policy" "bedrock_invoke" {
  name        = "rag-bedrock-invoke"
  description = "Allow API to invoke Bedrock models"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "api_bedrock" {
  role       = aws_iam_role.api_role.name
  policy_arn = aws_iam_policy.bedrock_invoke.arn
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

resource "aws_iam_role_policy_attachment" "chunker_s3" {
  role       = aws_iam_role.chunker_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

resource "aws_eks_pod_identity_association" "chunker" {
  cluster_name    = var.cluster_name
  namespace       = "rag-jobs"
  service_account = "chunker-sa"
  role_arn        = aws_iam_role.chunker_role.arn
}

resource "aws_iam_role" "indexer_role" {
  name               = "rag-indexer-role"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "indexer_sqs" {
  role       = aws_iam_role.indexer_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSQSFullAccess"
}

resource "aws_eks_pod_identity_association" "indexer" {
  cluster_name    = var.cluster_name
  namespace       = "rag-jobs"
  service_account = "indexer-sa"
  role_arn        = aws_iam_role.indexer_role.arn
}

# cilium-operator manages ENI IPAM (cilium.tf: ipam.mode=eni) and calls the EC2
# API directly to attach interfaces and assign IPs to new nodes. Without this,
# the operator falls back to the underlying EC2 instance's node-group role,
# which has no ec2:Describe*/CreateNetworkInterface permissions — new nodes
# then sit at "Waiting for IPs to become available" for minutes before a node
# is Ready.
resource "aws_iam_role" "cilium_operator_role" {
  name               = "rag-cilium-operator-role"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_policy" "cilium_eni" {
  name        = "rag-cilium-eni"
  description = "ENI IPAM permissions for cilium-operator (ipam.mode=eni)"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeSubnets",
          "ec2:DescribeVpcs",
          "ec2:DescribeVpcPeeringConnections",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeTags",
          "ec2:DescribeAvailabilityZones",
          "ec2:CreateTags",
          "ec2:CreateNetworkInterface",
          "ec2:AttachNetworkInterface",
          "ec2:DetachNetworkInterface",
          "ec2:DeleteNetworkInterface",
          "ec2:AssignPrivateIpAddresses",
          "ec2:UnassignPrivateIpAddresses",
          "ec2:ModifyNetworkInterfaceAttribute",
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cilium_operator_eni" {
  role       = aws_iam_role.cilium_operator_role.name
  policy_arn = aws_iam_policy.cilium_eni.arn
}

resource "aws_eks_pod_identity_association" "cilium_operator" {
  cluster_name    = var.cluster_name
  namespace       = "kube-system"
  service_account = "cilium-operator"
  role_arn        = aws_iam_role.cilium_operator_role.arn
}
