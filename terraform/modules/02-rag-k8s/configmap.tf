resource "kubernetes_namespace" "rag_jobs" {
  metadata {
    name = "rag-jobs"
  }
}

resource "kubernetes_config_map" "sqs_urls" {
  metadata {
    name      = "sqs-config"
    namespace = kubernetes_namespace.rag_jobs.metadata[0].name
  }

  data = {
    CHUNKER_SQS_URL = var.sqs_chunker_url
    INDEXER_SQS_URL = var.sqs_indexer_url
  }
}
