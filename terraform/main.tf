module "rag_storage" {
  source = "./modules/rag_storage"

  # TODO: Replace with a globally unique bucket name.
  # Using a placeholder variable or hardcoded string here for demonstration.
  bucket_name = "my-unique-rag-docs-bucket-12345"

  queue_name = "rag-upload-notifications"

  tags = {
    Environment = "dev"
    Project     = "simple-rag"
  }
}

output "rag_s3_bucket" {
  value = module.rag_storage.s3_bucket_name
}

output "rag_sqs_queue" {
  value = module.rag_storage.sqs_queue_url
}
