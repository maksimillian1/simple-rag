terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
}

provider "helm" {
  kubernetes {
    host                   = var.is_local_test ? null : module.rag_core.eks_cluster_endpoint
    cluster_ca_certificate = var.is_local_test ? null : try(base64decode(module.rag_core.eks_cluster_certificate_authority_data), null)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = var.is_local_test ? null : ["eks", "get-token", "--cluster-name", module.rag_core.cluster_name]
    }
  }
}

provider "aws" {
  region = var.aws_region
}
