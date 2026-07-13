#!/bin/bash

echo "Force-deleting all ArgoCD applications..."

APPS=$(kubectl get applications -n argocd -o name)

if [ -z "$APPS" ]; then
  echo "No applications found in the argocd namespace."
  exit 0
fi

for app in $APPS; do
  echo "Patching $app..."
  kubectl patch $app -n argocd --type merge -p '{"metadata":{"finalizers":null}}'
done

echo "All finalizers removed!"
