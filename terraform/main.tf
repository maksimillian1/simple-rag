module "rag_storage" {
  source = "./modules/rag_storage"

  resource_prefix      = var.resource_prefix
  is_local_test        = var.is_local_test
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway   = var.single_nat_gateway

  tags = {
    app         = "simple-rag"
    environment = var.is_local_test ? "local-test" : "dev"
    managed-by  = "terraform"
  }
}

output "rag_s3_bucket" {
  value = module.rag_storage.s3_bucket_name
}

output "rag_s3_bucket_arn" {
  value = module.rag_storage.s3_bucket_arn
}

output "rag_sqs_queue" {
  value = module.rag_storage.sqs_stage_1_queue_url
}

output "rag_sqs_stage_1_queue" {
  value = module.rag_storage.sqs_stage_1_queue_url
}

output "rag_sqs_stage_1_queue_arn" {
  value = module.rag_storage.sqs_stage_1_queue_arn
}

output "rag_sqs_stage_2_queue" {
  value = module.rag_storage.sqs_stage_2_queue_url
}

output "rag_sqs_stage_2_queue_arn" {
  value = module.rag_storage.sqs_stage_2_queue_arn
}

output "vpc_id" {
  value = module.rag_storage.vpc_id
}

output "private_subnets" {
  value = module.rag_storage.private_subnets
}

output "public_subnets" {
  value = module.rag_storage.public_subnets
}
