data "http" "aws_lbc_gateway_crds" {
  url = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/refs/heads/main/config/crd/gateway/gateway-crds.yaml"
}

data "kubectl_file_documents" "aws_lbc_gateway_crds" {
  content = data.http.aws_lbc_gateway_crds.response_body
}

resource "kubectl_manifest" "aws_lbc_gateway_crds" {
  for_each          = data.kubectl_file_documents.aws_lbc_gateway_crds.manifests
  yaml_body         = each.value
  server_side_apply = true
  depends_on = [helm_release.gateway_api_crds]
}
