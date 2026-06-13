package debug

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/labstack/echo/v4"
	"github.com/qdrant/fastembed-go"
	"github.com/qdrant/go-client/qdrant"
)

//go:embed seed_data.json
var seedDataJSON []byte

type Service struct {
	Environment          string
	SQSQueueURL          string
	QdrantURL            string
	EmbeddingModelTeiURL string
	Collection           string
	DenseVectorsName     string
	SparseVectorsName    string
	QdrantClient         *qdrant.Client
	SparseModel          *fastembed.SparseEmbeddingModel
}

func NewService(environment, sqsQueueURL, qdrantURL, embeddingModelTeiURL, collection string, denseName, sparseName string, qdrantClient *qdrant.Client, sparseModel *fastembed.SparseEmbeddingModel) *Service {
	return &Service{
		Environment:          environment,
		SQSQueueURL:          sqsQueueURL,
		QdrantURL:            qdrantURL,
		EmbeddingModelTeiURL: embeddingModelTeiURL,
		Collection:           collection,
		DenseVectorsName:     denseName,
		SparseVectorsName:    sparseName,
		QdrantClient:         qdrantClient,
		SparseModel:          sparseModel,
	}
}

type SeedItem struct {
	Text     string `json:"text"`
	Source   string `json:"source"`
	Category string `json:"category"`
}

type SparseVector struct {
	Indices []uint32  `json:"indices"`
	Values  []float64 `json:"values"`
}

type QdrantPoint struct {
	ID      interface{}            `json:"id"`
	Vector  map[string]interface{} `json:"vector"`
	Payload map[string]interface{} `json:"payload"`
}

type QdrantUpsertRequest struct {
	Points []QdrantPoint `json:"points"`
}

func (s *Service) SeedHandler(c echo.Context) error {
	if s.Environment != "dev" {
		return c.String(http.StatusForbidden, "Forbidden in non-dev environment")
	}

	log.Println("[INFO] [debug] Starting native Go-based database seeder...")

	var items []SeedItem
	if err := json.Unmarshal(seedDataJSON, &items); err != nil {
		log.Printf("[ERROR] [debug] Failed to parse embedded seed_data.json: %v", err)
		return c.String(http.StatusInternalServerError, "Failed to parse seed data: "+err.Error())
	}

	log.Printf("[INFO] [debug] Loaded %d items from seed_data.json", len(items))

	client := http.Client{Timeout: 10 * time.Second}

	reqDel, _ := http.NewRequest(http.MethodDelete, s.QdrantURL+"/collections/"+s.Collection, nil)
	respDel, err := client.Do(reqDel)
	if err == nil {
		respDel.Body.Close()
		log.Printf("[INFO] [debug] Cleaned up existing collection '%s'", s.Collection)
	}

	createPayload := map[string]interface{}{
		"vectors": map[string]interface{}{
			s.DenseVectorsName: map[string]interface{}{
				"size":     384,
				"distance": "Cosine",
			},
		},
		"sparse_vectors": map[string]interface{}{
			s.SparseVectorsName: map[string]interface{}{},
		},
	}
	createBytes, _ := json.Marshal(createPayload)
	reqCreate, err := http.NewRequest(http.MethodPut, s.QdrantURL+"/collections/"+s.Collection, bytes.NewBuffer(createBytes))
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to create collection request: %v", err)
		return c.String(http.StatusInternalServerError, "Internal Server Error")
	}
	reqCreate.Header.Set("Content-Type", "application/json")
	respCreate, err := client.Do(reqCreate)
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to connect to Qdrant to create collection: %v", err)
		return c.String(http.StatusServiceUnavailable, "Failed to connect to Qdrant: "+err.Error())
	}
	defer respCreate.Body.Close()
	if respCreate.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(respCreate.Body)
		log.Printf("[ERROR] [debug] Qdrant collection creation failed with status %d: %s", respCreate.StatusCode, string(body))
		return c.String(http.StatusInternalServerError, "Failed to create Qdrant collection: "+string(body))
	}
	log.Printf("[INFO] [debug] Successfully created collection '%s'", s.Collection)

	log.Println("[INFO] [debug] Generating embeddings from TEI concurrently...")
	type job struct {
		id   int
		item SeedItem
	}
	type result struct {
		point QdrantPoint
		err   error
	}

	numJobs := len(items)
	jobs := make(chan job, numJobs)
	results := make(chan result, numJobs)

	var wg sync.WaitGroup
	numWorkers := 5
	for w := 1; w <= numWorkers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := range jobs {
				vector, err := s.getEmbedding(j.item.Text)
				if err != nil {
					results <- result{err: fmt.Errorf("item %d failed: %w", j.id, err)}
					continue
				}

				embeddings, err := s.SparseModel.Embed(context.Background(), []string{j.item.Text})
				if err != nil {
					results <- result{err: fmt.Errorf("item %d sparse embedding failed: %w", j.id, err)}
					continue
				}
				if len(embeddings) == 0 {
					results <- result{err: fmt.Errorf("item %d no sparse embedding generated", j.id)}
					continue
				}
				sparseEmbedding := embeddings[0]

				sparseIndices := sparseEmbedding.Indices
				sparseValues := make([]float64, len(sparseEmbedding.Values))
				for idx, val := range sparseEmbedding.Values {
					sparseValues[idx] = float64(val)
				}

				results <- result{
					point: QdrantPoint{
						ID:     j.id,
						Vector: map[string]interface{}{
							s.DenseVectorsName: vector,
							s.SparseVectorsName: map[string]interface{}{
								"indices": sparseIndices,
								"values":  sparseValues,
							},
						},
						Payload: map[string]interface{}{
							"text":     j.item.Text,
							"source":   j.item.Source,
							"category": j.item.Category,
						},
					},
				}
			}
		}()
	}

	for i, item := range items {
		jobs <- job{id: i + 1, item: item}
	}
	close(jobs)

	go func() {
		wg.Wait()
		close(results)
	}()

	var points []QdrantPoint
	var firstErr error
	for res := range results {
		if res.err != nil {
			if firstErr == nil {
				firstErr = res.err
			}
			log.Printf("[ERROR] [debug] Embedding worker error: %v", res.err)
		} else {
			points = append(points, res.point)
		}
	}

	if firstErr != nil {
		log.Printf("[ERROR] [debug] Seeding aborted because one or more embeddings failed: %v", firstErr)
		return c.String(http.StatusInternalServerError, "Seeding failed during embedding generation: "+firstErr.Error())
	}

	log.Printf("[INFO] [debug] Generated embeddings for %d points. Upserting to Qdrant...", len(points))

	upsertPayload := QdrantUpsertRequest{Points: points}
	upsertBytes, err := json.Marshal(upsertPayload)
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to marshal upsert payload: %v", err)
		return c.String(http.StatusInternalServerError, "Failed to build Qdrant upsert payload")
	}

	reqUpsert, err := http.NewRequest(http.MethodPut, s.QdrantURL+"/collections/"+s.Collection+"/points?wait=true", bytes.NewBuffer(upsertBytes))
	if err != nil {
		return c.String(http.StatusInternalServerError, "Internal Server Error")
	}
	reqUpsert.Header.Set("Content-Type", "application/json")
	respUpsert, err := client.Do(reqUpsert)
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to connect to Qdrant for upsert: %v", err)
		return c.String(http.StatusServiceUnavailable, "Failed to upsert points: "+err.Error())
	}
	defer respUpsert.Body.Close()

	if respUpsert.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(respUpsert.Body)
		log.Printf("[ERROR] [debug] Qdrant points upsert failed with status %d: %s", respUpsert.StatusCode, string(body))
		return c.String(http.StatusInternalServerError, "Failed to upsert points into Qdrant collection")
	}

	log.Printf("[INFO] [debug] Database seeding completed successfully! Inserted %d points.", len(points))
	return c.JSON(http.StatusOK, map[string]interface{}{
		"status":  "ok",
		"message": fmt.Sprintf("Successfully seeded %d items into Qdrant collection '%s' using TEI embeddings.", len(points), s.Collection),
	})
}

func (s *Service) getEmbedding(text string) ([]float32, error) {
	teiPayload, err := json.Marshal(map[string]string{"inputs": text})
	if err != nil {
		return nil, err
	}

	client := http.Client{Timeout: 10 * time.Second}
	teiResp, err := client.Post(s.EmbeddingModelTeiURL+"/embed", "application/json", bytes.NewBuffer(teiPayload))
	if err != nil {
		return nil, err
	}
	defer teiResp.Body.Close()

	if teiResp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(teiResp.Body)
		return nil, fmt.Errorf("TEI returned status %d: %s", teiResp.StatusCode, string(bodyBytes))
	}

	var embedRes interface{}
	if err := json.NewDecoder(teiResp.Body).Decode(&embedRes); err != nil {
		return nil, err
	}

	var vector []float32
	switch val := embedRes.(type) {
	case []interface{}:
		if len(val) > 0 {
			if first, ok := val[0].([]interface{}); ok {
				vector = make([]float32, len(first))
				for i, v := range first {
					f, _ := v.(float64)
					vector[i] = float32(f)
				}
			} else {
				vector = make([]float32, len(val))
				for i, v := range val {
					f, _ := v.(float64)
					vector[i] = float32(f)
				}
			}
		}
	}

	if len(vector) == 0 {
		return nil, fmt.Errorf("failed to parse vector from TEI response: %+v", embedRes)
	}

	return vector, nil
}

func (s *Service) IndexHandler(c echo.Context) error {
	if s.Environment != "dev" {
		return c.String(http.StatusForbidden, "Forbidden in non-dev environment")
	}

	type IndexRequest struct {
		Text string `json:"text"`
	}

	var req IndexRequest
	if err := c.Bind(&req); err != nil {
		return c.String(http.StatusBadRequest, "Invalid Request Body: "+err.Error())
	}

	reqText := strings.TrimSpace(req.Text)
	if reqText == "" {
		return c.String(http.StatusBadRequest, "Text content cannot be empty")
	}

	payload := map[string]interface{}{
		"trace_id": "manual-debug-trace-id",
		"document": map[string]interface{}{
			"file_id":   "doc_manual_web",
			"file_name": "manual_web_input",
		},
		"boundaries": map[string]interface{}{
			"part_index":  0,
			"total_parts": 1,
		},
		"chunks": []map[string]interface{}{
			{
				"chunk_index": 0,
				"page_number": 1,
				"content":     reqText,
			},
		},
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return c.String(http.StatusInternalServerError, "Failed to marshal payload")
	}

	if !strings.Contains(s.SQSQueueURL, "localhost") && !strings.Contains(s.SQSQueueURL, "127.0.0.1") {
		os.Setenv("AWS_IGNORE_CONFIGURED_ENDPOINT_URLS", "true")
		defer os.Unsetenv("AWS_IGNORE_CONFIGURED_ENDPOINT_URLS")
	}

	cfg, err := config.LoadDefaultConfig(c.Request().Context())
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to load AWS config: %v", err)
		return c.String(http.StatusInternalServerError, "Failed to load AWS configuration: "+err.Error())
	}

	sqsClient := sqs.NewFromConfig(cfg)
	_, err = sqsClient.SendMessage(c.Request().Context(), &sqs.SendMessageInput{
		QueueUrl:    aws.String(s.SQSQueueURL),
		MessageBody: aws.String(string(payloadBytes)),
	})
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to send message to SQS: %v", err)
		return c.String(http.StatusInternalServerError, "Failed to send message to SQS queue: "+err.Error())
	}

	return c.JSON(http.StatusOK, map[string]string{
		"status":  "ok",
		"message": "Manual chunk successfully sent to SQS queue. The continuous indexer worker will pull and process it in a few seconds.",
	})
}
