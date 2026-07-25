#!/bin/bash
# Extracts the initial ArgoCD admin password
echo "Fetching ArgoCD initial admin password..."
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
echo ""
