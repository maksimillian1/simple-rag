resource "random_id" "qdrant_backup_suffix" {
  byte_length = 6
}

locals {
  qdrant_backup_bucket_name = "qdrant-backups-${var.resource_prefix}-${random_id.qdrant_backup_suffix.hex}"
}

# S3 Bucket for Qdrant Backups
resource "aws_s3_bucket" "qdrant_backup" {
  bucket        = local.qdrant_backup_bucket_name
  force_destroy = var.is_local_test

  tags = local.merged_tags
}

# Ensure the S3 bucket is completely private
resource "aws_s3_bucket_public_access_block" "qdrant_backup_public_access" {
  bucket = aws_s3_bucket.qdrant_backup.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-KMS Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "qdrant_backup_sse" {
  bucket = aws_s3_bucket.qdrant_backup.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

# Lifecycle policy: Transition to Glacier Deep Archive after 90 days
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

# IAM Role for KubeBlocks Qdrant Backup Manager (IRSA)
data "aws_iam_policy_document" "qdrant_backup_assume_role" {
  count = var.is_local_test ? 0 : 1

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [try(one(module.eks[*].oidc_provider_arn), "")]
    }
    condition {
      test     = "StringEquals"
      variable = "${try(one(module.eks[*].oidc_provider), "")}:sub"
      values   = ["system:serviceaccount:rag-platform:qdrant-backup-sa"]
    }
  }
}

resource "aws_iam_role" "qdrant_backup_role" {
  count              = var.is_local_test ? 0 : 1
  name               = "${var.resource_prefix}-qdrant-backup-role"
  assume_role_policy = data.aws_iam_policy_document.qdrant_backup_assume_role[0].json

  tags = local.merged_tags
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
  count  = var.is_local_test ? 0 : 1
  name   = "${var.resource_prefix}-qdrant-backup-policy"
  role   = aws_iam_role.qdrant_backup_role[0].id
  policy = data.aws_iam_policy_document.qdrant_backup_policy.json
}
