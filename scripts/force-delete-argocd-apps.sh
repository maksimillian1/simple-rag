#!/usr/bin/env bash
set -e

NAMESPACE="argocd"

echo "=== 1. Stripping finalizers from underlying Storage & Workloads (PVCs, PVs, StatefulSets) ==="
# Снимаем защиту kubernetes.io/pvc-protection со всех PVC во всех неймспейсах
kubectl get pvc --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' 2>/dev/null | while read -r ns name; do
  [ -z "$name" ] && continue
  echo "Patching PVC: $ns/$name"
  kubectl patch pvc "$name" -n "$ns" --type merge -p '{"metadata":{"finalizers":[]}}' 2>/dev/null || true
done

# Снимаем защиту kubernetes.io/pv-protection со всех PV
kubectl get pv -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n' | while read -r pv; do
  [ -z "$pv" ] && continue
  echo "Patching PV: $pv"
  kubectl patch pv "$pv" --type merge -p '{"metadata":{"finalizers":[]}}' 2>/dev/null || true
done

echo "=== 2. Stripping finalizers from ArgoCD Custom Resources ==="
for crd in applicationsets.argoproj.io applications.argoproj.io appprojects.argoproj.io; do
  echo "Processing CRD: $crd"
  kubectl get $crd -n $NAMESPACE -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n' | while read -r res; do
    [ -z "$res" ] && continue
    # Удаляем finalizer "resources-finalizer.argocd.argoproj.io"
    kubectl patch $crd "$res" -n $NAMESPACE --type json -p='[{"op": "remove", "path": "/metadata/finalizers"}]' 2>/dev/null || \
    kubectl patch $crd "$res" -n $NAMESPACE --type merge -p='{"metadata":{"finalizers":[]}}' 2>/dev/null || true
  done
done

echo "=== 3. Force-deleting ArgoCD Application resources (Orphan Delete) ==="
# Флаг --cascade=orphan принудительно отвязывает ресурсы K8s от ArgoCD без попытки их каскадного удаления
kubectl delete applicationsets --all -n $NAMESPACE --cascade=orphan --force --grace-period=0 2>/dev/null || true
kubectl delete applications --all -n $NAMESPACE --cascade=orphan --force --grace-period=0 2>/dev/null || true
kubectl delete appprojects --all -n $NAMESPACE --force --grace-period=0 2>/dev/null || true

echo "=== 4. Clearing stuck API objects ==="
kubectl get applications,applicationsets,appprojects -n $NAMESPACE -o name 2>/dev/null | grep -v "appproject.argoproj.io/default" | while read -r res; do
  [ -z "$res" ] && continue
  echo "Hard cleaning: $res"
  kubectl patch "$res" -n $NAMESPACE --type merge -p '{"metadata":{"finalizers":[]}}' 2>/dev/null || true
  kubectl delete "$res" -n $NAMESPACE --force --grace-period=0 2>/dev/null || true
done

echo "=== SUCCESS! All ArgoCD dependencies and PVC finalizers are wiped. Run 'terraform destroy' now. ==="
