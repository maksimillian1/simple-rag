#!/bin/bash
APP_NAME=${1:-root-bootstrap}
REVISION=${2:-HEAD}

echo "Force syncing ArgoCD Application: $APP_NAME to revision: $REVISION"
kubectl patch application "$APP_NAME" -n argocd --type merge -p "{\"operation\": {\"sync\": {\"revision\": \"$REVISION\"}}}"
