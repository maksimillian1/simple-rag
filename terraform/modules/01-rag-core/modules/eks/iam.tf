resource "aws_iam_role" "karpenter_node" {
  name = "${var.cluster_name}-karpenter-node"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "karpenter_node_policies" {
  for_each = {
    worker = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
    cni    = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
    ecr    = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
    ssm    = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }

  role       = aws_iam_role.karpenter_node.name
  policy_arn = each.value
}

resource "aws_iam_instance_profile" "karpenter_node" {
  name = "${var.cluster_name}-karpenter-node"
  role = aws_iam_role.karpenter_node.name

  tags = var.tags
}

resource "aws_iam_policy" "karpenter_controller" {
  name        = "${var.cluster_name}-karpenter-controller"
  description = "IAM Policy for Karpenter Controller"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "ec2:CreateFleet",
          "ec2:CreateLaunchTemplate",
          "ec2:CreateTags",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeImages",
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceTypeOfferings",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeLaunchTemplates",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeSubnets",
          "ec2:RunInstances",
          "ec2:TerminateInstances",
          "ec2:DeleteLaunchTemplate",
          "ssm:GetParameter",
          "pricing:GetProducts",
          "iam:AddRoleToInstanceProfile",
          "iam:CreateInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:GetInstanceProfile",
          "iam:RemoveRoleFromInstanceProfile",
          "iam:TagInstanceProfile"
        ]
        Effect   = "Allow"
        Resource = "*"
      },
      {
        Action = [
          "iam:CreateServiceLinkedRole"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:iam::*:role/aws-service-role/spot.amazonaws.com/AWSServiceRoleForEC2Spot*"
        Condition = {
          StringEquals = {
            "iam:AWSServiceName" = "spot.amazonaws.com"
          }
        }
      },
      {
        Action = [
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl",
          "sqs:ReceiveMessage"
        ]
        Effect   = "Allow"
        Resource = aws_sqs_queue.karpenter_interruption.arn
      },
      {
        Action = [
          "iam:PassRole"
        ]
        Effect   = "Allow"
        Resource = aws_iam_role.karpenter_node.arn
      },
      {
        Action = [
          "eks:DescribeCluster"
        ]
        Effect   = "Allow"
        Resource = module.eks.cluster_arn
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role" "karpenter_controller" {
  name = "${var.cluster_name}-karpenter-controller"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = module.eks.oidc_provider_arn
        }
        Condition = {
          StringEquals = {
            "${module.eks.oidc_provider}:sub" = "system:serviceaccount:karpenter:karpenter"
            "${module.eks.oidc_provider}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "karpenter_controller" {
  role       = aws_iam_role.karpenter_controller.name
  policy_arn = aws_iam_policy.karpenter_controller.arn
}

resource "aws_eks_access_entry" "karpenter_node" {
  cluster_name  = module.eks.cluster_name
  principal_arn = aws_iam_role.karpenter_node.arn
  type          = "EC2_LINUX"
}


