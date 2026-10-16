#!/bin/bash
echo "Starting safe cluster teardown..."

CLUSTER_NAME=${CLUSTER_NAME:-$(kubectl config view --minify -o jsonpath='{.clusters[0].name}' 2>/dev/null | awk -F/ '{print $NF}')}
DATA_NAMESPACES="rag-platform monitoring"

echo "1. Stopping ArgoCD reconciliation so self-heal does not re-create deleted workloads..."
kubectl -n argocd scale statefulset argocd-application-controller --replicas=0
kubectl -n argocd scale deployment argocd-applicationset-controller --replicas=0

echo "2. Deleting namespaces that own persistent volumes ($DATA_NAMESPACES) while EBS CSI is still running..."
kubectl delete namespace $DATA_NAMESPACES --ignore-not-found --wait=true --timeout=10m

echo "3. Waiting for dynamically provisioned volumes to be deleted..."
kubectl wait --for=delete pv --all --timeout=5m || kubectl get pv

echo "4. Force removing finalizers from all ArgoCD applications to prevent hanging..."
APPS=$(kubectl get applications -n argocd -o name 2>/dev/null)
if [ ! -z "$APPS" ]; then
  for app in $APPS; do
    echo "   Patching $app..."
    kubectl patch $app -n argocd --type merge -p '{"metadata":{"finalizers":null}}'
  done
else
  echo "   No ArgoCD applications found. Skipping."
fi

echo "5. Deleting root-bootstrap application..."
kubectl delete application root-bootstrap -n argocd --ignore-not-found

echo "6. Waiting 10 seconds for cloud load-balancers to reconcile..."
sleep 10

echo "7. Triggering Terraform Destroy..."
cd terraform || exit
terraform destroy

echo "8. Deleting EBS volumes left unattached by cluster '$CLUSTER_NAME'..."
if [ "$KEEP_VOLUMES" = "1" ] || [ -z "$CLUSTER_NAME" ]; then
  echo "   Skipped (KEEP_VOLUMES=1 or cluster name unknown)."
else
  LEFTOVER=$(aws ec2 describe-volumes \
    --filters Name=status,Values=available Name=tag-key,Values=kubernetes.io/cluster/$CLUSTER_NAME \
    --query 'Volumes[].VolumeId' --output text)
  if [ -z "$LEFTOVER" ]; then
    echo "   None left."
  fi
  for vol in $LEFTOVER; do
    echo "   Deleting $vol..."
    aws ec2 delete-volume --volume-id "$vol"
  done
fi
