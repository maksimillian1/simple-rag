#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -euo pipefail

QDRANT_URL="http://localhost:6333"
COLLECTION_NAME="demo_collection"

echo "=== Checking Qdrant availability ==="
until curl -s "$QDRANT_URL/readyz" > /dev/null; do
  echo "Waiting for Qdrant to start at $QDRANT_URL..."
  sleep 2
done
echo "Qdrant is ready!"

echo "=== Deleting collection '$COLLECTION_NAME' if it exists (for idempotency) ==="
curl -s -X DELETE "$QDRANT_URL/collections/$COLLECTION_NAME" || true
echo ""

echo "=== Creating collection '$COLLECTION_NAME' (Vector Size: 4, Metric: Cosine) ==="
curl -s -X PUT "$QDRANT_URL/collections/$COLLECTION_NAME" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 4,
      "distance": "Cosine"
    }
  }'
echo ""
echo ""

echo "=== Seeding demo points (vectors + payload metadata) ==="
curl -s -X PUT "$QDRANT_URL/collections/$COLLECTION_NAME/points?wait=true" \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {
        "id": 1,
        "vector": [0.1, 0.2, 0.3, 0.4],
        "payload": {
          "text": "AWS S3 serves as our primary document ingestion window where external systems upload documents.",
          "source": "s3_ingestion",
          "category": "infrastructure"
        }
      },
      {
        "id": 2,
        "vector": [0.9, 0.1, 0.1, 0.1],
        "payload": {
          "text": "Qdrant was selected as our vector storage due to its excellent performance-to-efficiency ratio and low latency.",
          "source": "vector_storage_adr",
          "category": "database"
        }
      },
      {
        "id": 3,
        "vector": [0.2, 0.8, 0.1, 0.1],
        "payload": {
          "text": "The indexer is deployed as a short-lived Kubernetes job managed by KEDA to minimize continuous compute costs.",
          "source": "indexer_keda",
          "category": "deployment"
        }
      }
    ]
  }'
echo ""
echo ""
echo "=== Seeding completed successfully! ==="
