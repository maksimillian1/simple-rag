resource "helm_release" "cilium" {

  name       = "cilium"
  repository = "https://helm.cilium.io/"
  chart      = "cilium"
  version    = "1.19.5"
  namespace  = "kube-system"
  wait       = false

  set {
    name  = "eni.enabled"
    value = "true"
  }


  set {
    name  = "gatewayAPI.enabled"
    value = "true"
  }

  set {
    name  = "operator.removeNodeTaints"
    value = "true"
  }

  set {
    name  = "ipam.mode"
    value = "eni"
  }

  set {
    name  = "routingMode"
    value = "native"
  }

  set {
    name  = "k8sServiceHost"
    value = replace(var.cluster_endpoint, "https://", "")
  }

  set {
    name  = "k8sServicePort"
    value = "443"
  }

  set {
    name  = "egressGateway.enabled"
    value = "true"
  }

  set {
    name  = "bpf.masquerade"
    value = "true"
  }

  set {
    name  = "enableIPv4Masquerade"
    value = "true"
  }

  set {
    name  = "nodePort.enabled"
    value = "true"
  }

  set {
    name  = "kubeProxyReplacement"
    value = "true"
  }

  set {
    name  = "operator.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].key"
    value = "eks.amazonaws.com/compute-type"
  }
  set {
    name  = "operator.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].operator"
    value = "NotIn"
  }
  set {
    name  = "operator.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].values[0]"
    value = "fargate"
  }

  set {
    name  = "affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].key"
    value = "eks.amazonaws.com/compute-type"
  }
  set {
    name  = "affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].operator"
    value = "NotIn"
  }
  set {
    name  = "affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].values[0]"
    value = "fargate"
  }
}
