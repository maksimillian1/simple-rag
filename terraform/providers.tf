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
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = ">= 1.19.0"
    }
  }
}

locals {
  k8s_host = var.is_local_test ? null : module.rag_core.eks_cluster_endpoint
  k8s_ca   = var.is_local_test ? null : try(base64decode(module.rag_core.eks_cluster_certificate_authority_data), null)
  k8s_args = var.is_local_test ? null : ["eks", "get-token", "--cluster-name", module.rag_core.cluster_name]
}

provider "helm" {
  kubernetes {
    host                   = local.k8s_host
    cluster_ca_certificate = local.k8s_ca

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = local.k8s_args
    }
  }
}

provider "kubernetes" {
  host                   = local.k8s_host
  cluster_ca_certificate = local.k8s_ca

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = local.k8s_args
  }
}

provider "kubectl" {
  host                   = local.k8s_host
  cluster_ca_certificate = local.k8s_ca
  load_config_file       = false

  dynamic "exec" {
    for_each = var.is_local_test ? [] : [1]
    content {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = local.k8s_args
    }
  }
}

provider "aws" {
  region = var.aws_region
}
