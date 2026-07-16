resource "random_id" "qdrant_backup_suffix" {
  byte_length = 6
}

locals {
  qdrant_backup_bucket_name = "qdrant-backups-${var.resource_prefix}-${random_id.qdrant_backup_suffix.hex}"
}

resource "aws_s3_bucket" "qdrant_backup" {
  bucket        = local.qdrant_backup_bucket_name
  force_destroy = false

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "qdrant_backup_public_access" {
  bucket = aws_s3_bucket.qdrant_backup.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "qdrant_backup_sse" {
  bucket = aws_s3_bucket.qdrant_backup.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "qdrant_backup_lifecycle" {
  bucket = aws_s3_bucket.qdrant_backup.id

  rule {
    id     = "transition-to-glacier-deep-archive"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "DEEP_ARCHIVE"
    }
  }
}

data "aws_iam_policy_document" "qdrant_backup_assume_role" {
  statement {
    actions = [
      "sts:AssumeRole",
      "sts:TagSession"
    ]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "qdrant_backup_role" {
  name               = "${var.resource_prefix}-qdrant-backup-role"
  assume_role_policy = data.aws_iam_policy_document.qdrant_backup_assume_role.json

  tags = var.tags
}

data "aws_iam_policy_document" "qdrant_backup_policy" {
  statement {
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.qdrant_backup.arn,
      "${aws_s3_bucket.qdrant_backup.arn}/*"
    ]
  }
}

resource "aws_iam_role_policy" "qdrant_backup_role_policy" {
  name   = "${var.resource_prefix}-qdrant-backup-policy"
  role   = aws_iam_role.qdrant_backup_role.id
  policy = data.aws_iam_policy_document.qdrant_backup_policy.json
}

resource "aws_eks_pod_identity_association" "qdrant_backup" {
  cluster_name    = var.cluster_name
  namespace       = "rag-platform"
  service_account = "qdrant-backup-sa"
  role_arn        = aws_iam_role.qdrant_backup_role.arn
}

resource "kubernetes_config_map" "qdrant_infra_config" {
  metadata {
    name      = "qdrant-infra-config"
    namespace = "rag-platform"
  }

  data = {
    QDRANT_BACKUP_BUCKET_NAME = aws_s3_bucket.qdrant_backup.id
  }

  depends_on = [
    helm_release.root_application
  ]
}
