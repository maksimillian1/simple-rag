#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -euo pipefail

QDRANT_URL="http://localhost:6333"
TEI_URL="http://localhost:8081"
COLLECTION_NAME="demo_collection"

echo "=== Checking Qdrant availability ==="
until curl -s "$QDRANT_URL/readyz" > /dev/null; do
  echo "Waiting for Qdrant to start at $QDRANT_URL..."
  sleep 2
done
echo "Qdrant is ready!"

echo "=== Checking TEI availability ==="
until curl -s "$TEI_URL/health" > /dev/null; do
  echo "Waiting for TEI to start at $TEI_URL..."
  sleep 2
done
echo "TEI is ready!"

echo "=== Deleting collection '$COLLECTION_NAME' if it exists (for idempotency) ==="
curl -s -X DELETE "$QDRANT_URL/collections/$COLLECTION_NAME" || true
echo ""

echo "=== Creating collection '$COLLECTION_NAME' (Vector Size: 384, Metric: Cosine) ==="
curl -s -X PUT "$QDRANT_URL/collections/$COLLECTION_NAME" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 384,
      "distance": "Cosine"
    }
  }'
echo ""
echo ""

# Helper to generate embeddings using TEI through standard Python
generate_embedding() {
  local text="$1"
  python3 -c "
import urllib.request
import json
import sys

text = sys.argv[1]
url = '${TEI_URL}/embed'
payload = json.dumps({'inputs': text}).encode('utf-8')
req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req) as f:
        res = json.loads(f.read().decode('utf-8'))
        # If response is a list of lists, take the first one; if list of floats, print directly
        if isinstance(res, list) and len(res) > 0 and isinstance(res[0], list):
            print(json.dumps(res[0]))
        else:
            print(json.dumps(res))
except Exception as e:
    print(f'Error calling TEI: {e}', file=sys.stderr)
    sys.exit(1)
" "$text"
}

echo "=== Generating embeddings dynamically from TEI ==="
echo "Generating Vector 1..."
VEC1=$(generate_embedding "AWS S3 serves as our primary document ingestion window where external systems upload documents.")

echo "Generating Vector 2..."
VEC2=$(generate_embedding "Qdrant was selected as our vector storage due to its excellent performance-to-efficiency ratio and low latency.")

echo "Generating Vector 3..."
VEC3=$(generate_embedding "The indexer is deployed as a short-lived Kubernetes job managed by KEDA to minimize continuous compute costs.")

echo "=== Seeding demo points (vectors + payload metadata) ==="
curl -s -X PUT "$QDRANT_URL/collections/$COLLECTION_NAME/points?wait=true" \
  -H "Content-Type: application/json" \
  -d "{
    \"points\": [
      {
        \"id\": 1,
        \"vector\": $VEC1,
        \"payload\": {
          \"text\": \"AWS S3 serves as our primary document ingestion window where external systems upload documents.\",
          \"source\": \"s3_ingestion\",
          \"category\": \"infrastructure\"
        }
      },
      {
        \"id\": 2,
        \"vector\": $VEC2,
        \"payload\": {
          \"text\": \"Qdrant was selected as our vector storage due to its excellent performance-to-efficiency ratio and low latency.\",
          \"source\": \"vector_storage_adr\",
          \"category\": \"database\"
        }
      },
      {
        \"id\": 3,
        \"vector\": $VEC3,
        \"payload\": {
          \"text\": \"The indexer is deployed as a short-lived Kubernetes job managed by KEDA to minimize continuous compute costs.\",
          \"source\": \"indexer_keda\",
          \"category\": \"deployment\"
        }
      }
    ]
  }"
echo ""
echo ""
echo "=== Seeding completed successfully! ==="
