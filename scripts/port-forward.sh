#!/bin/bash
# Port-forwarding for local UI access

echo "Starting port-forward for ArgoCD UI (localhost:8080)..."
kubectl port-forward svc/argocd-server -n argocd 8080:443 &
ARGOCD_PID=$!

echo "Starting port-forward for Qdrant UI (localhost:6333)..."
# Kubeblocks generates the service name based on the cluster. Usually clustername-qdrant
kubectl port-forward -n kb-system svc/qdrant-platform-qdrant 6333:6333 &
QDRANT_PID=$!

echo ""
echo "ArgoCD UI: https://localhost:8080"
echo "Qdrant UI: http://localhost:6333"
echo "Press Ctrl+C to stop port forwarding."

trap "kill $ARGOCD_PID $QDRANT_PID" EXIT
wait
