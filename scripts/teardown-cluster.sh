#!/bin/bash
echo "Starting safe cluster teardown..."

echo "1. Force removing finalizers from all ArgoCD applications to prevent hanging..."
APPS=$(kubectl get applications -n argocd -o name 2>/dev/null)
if [ ! -z "$APPS" ]; then
  for app in $APPS; do
    echo "   Patching $app..."
    kubectl patch $app -n argocd --type merge -p '{"metadata":{"finalizers":null}}'
  done
else
  echo "   No ArgoCD applications found. Skipping."
fi

echo "2. Deleting root-bootstrap application..."
kubectl delete application root-bootstrap -n argocd --ignore-not-found

echo "3. Waiting 10 seconds for cloud load-balancers to reconcile..."
sleep 10

echo "4. Triggering Terraform Destroy..."
cd terraform || exit
terraform destroy
