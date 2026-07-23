#!/bin/bash

echo "Forcefully cleaning up ArgoCD resources to unblock Terraform destroy..."

# 1. ApplicationSets
echo ""
echo "=== Stripping finalizers from ApplicationSets ==="
APPSETS=$(kubectl get applicationsets -n argocd -o name 2>/dev/null)
if [ -n "$APPSETS" ]; then
  for appset in $APPSETS; do
    echo "Forcefully removing finalizers from $appset..."
    kubectl patch $appset -n argocd --type merge -p '{"metadata":{"finalizers":null}}'
  done
else
  echo "No ApplicationSets found."
fi

# 2. Applications
echo ""
echo "=== Stripping finalizers from Applications ==="
APPS=$(kubectl get applications -n argocd -o name 2>/dev/null)
if [ -n "$APPS" ]; then
  for app in $APPS; do
    echo "Forcefully removing finalizers from $app..."
    kubectl patch $app -n argocd --type merge -p '{"metadata":{"finalizers":null}}'
  done
else
  echo "No Applications found."
fi

# 3. AppProjects
echo ""
echo "=== Stripping finalizers from AppProjects ==="
PROJECTS=$(kubectl get appprojects -n argocd -o name 2>/dev/null | grep -v "appproject.argoproj.io/default")
if [ -n "$PROJECTS" ]; then
  for proj in $PROJECTS; do
    echo "Forcefully removing finalizers from $proj..."
    kubectl patch $proj -n argocd --type merge -p '{"metadata":{"finalizers":null}}'
  done
else
  echo "No custom AppProjects found."
fi

echo "Done"
