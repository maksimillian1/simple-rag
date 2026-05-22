variable "bucket_name" {
  description = "Name of the S3 bucket for RAG documents. Must be globally unique."
  type        = string
}

variable "queue_name" {
  description = "Name of the SQS queue for RAG document processing notifications."
  type        = string
  default     = "rag-document-processing-queue"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
