resource "helm_release" "storage_class" {
  name       = "storage-class"
  chart      = "${path.module}/storage-class"
  namespace  = "kube-system"
  depends_on = [aws_eks_addon.aws_ebs_csi_driver]
}
