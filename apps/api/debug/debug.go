package debug

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"fmt"
	"hash/adler32"
	"io"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

//go:embed seed_data.json
var seedDataJSON []byte

type Service struct {
	Environment string
	SQSQueueURL string
	QdrantURL   string
	TeiURL      string
	Collection  string
}

func NewService(environment, sqsQueueURL, qdrantURL, teiURL, collection string) *Service {
	return &Service{
		Environment: environment,
		SQSQueueURL: sqsQueueURL,
		QdrantURL:   qdrantURL,
		TeiURL:      teiURL,
		Collection:  collection,
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

func computeSparseVector(text string) SparseVector {
	re := regexp.MustCompile(`\b[a-zA-Z0-9]{2,}\b`)
	words := re.FindAllString(strings.ToLower(text), -1)
	if len(words) == 0 {
		return SparseVector{Indices: []uint32{}, Values: []float64{}}
	}

	counts := make(map[string]int)
	for _, w := range words {
		counts[w]++
	}

	type item struct {
		index uint32
		value float64
	}
	var items []item
	totalWords := float64(len(words))

	for w, count := range counts {
		h := adler32.Checksum([]byte(w))
		index := h & 0x7fffffff
		value := float64(count) / totalWords
		items = append(items, item{index: index, value: value})
	}

	sort.Slice(items, func(i, j int) bool {
		return items[i].index < items[j].index
	})

	indices := make([]uint32, len(items))
	values := make([]float64, len(items))
	for i, it := range items {
		indices[i] = it.index
		values[i] = it.value
	}

	return SparseVector{Indices: indices, Values: values}
}

type QdrantPoint struct {
	ID      interface{}            `json:"id"`
	Vector  map[string]interface{} `json:"vector"`
	Payload map[string]interface{} `json:"payload"`
}

type QdrantUpsertRequest struct {
	Points []QdrantPoint `json:"points"`
}

func (s *Service) SeedHandler(w http.ResponseWriter, r *http.Request) {
	if s.Environment != "dev" {
		http.Error(w, "Forbidden in non-dev environment", http.StatusForbidden)
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}

	log.Println("[INFO] [debug] Starting native Go-based database seeder...")

	// 1. Parse embedded JSON items
	var items []SeedItem
	if err := json.Unmarshal(seedDataJSON, &items); err != nil {
		log.Printf("[ERROR] [debug] Failed to parse embedded seed_data.json: %v", err)
		http.Error(w, "Failed to parse seed data: "+err.Error(), http.StatusInternalServerError)
		return
	}

	log.Printf("[INFO] [debug] Loaded %d items from seed_data.json", len(items))

	client := http.Client{Timeout: 10 * time.Second}

	// 2. Delete collection if exists (idempotency)
	reqDel, _ := http.NewRequest(http.MethodDelete, s.QdrantURL+"/collections/"+s.Collection, nil)
	respDel, err := client.Do(reqDel)
	if err == nil {
		respDel.Body.Close()
		log.Printf("[INFO] [debug] Cleaned up existing collection '%s'", s.Collection)
	}

	// 3. Create collection with vector dimensions=384 and Cosine distance
	createPayload := map[string]interface{}{
		"vectors": map[string]interface{}{
			"dense": map[string]interface{}{
				"size":     384,
				"distance": "Cosine",
			},
		},
		"sparse_vectors": map[string]interface{}{
			"sparse": map[string]interface{}{},
		},
	}
	createBytes, _ := json.Marshal(createPayload)
	reqCreate, err := http.NewRequest(http.MethodPut, s.QdrantURL+"/collections/"+s.Collection, bytes.NewBuffer(createBytes))
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to create collection request: %v", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}
	reqCreate.Header.Set("Content-Type", "application/json")
	respCreate, err := client.Do(reqCreate)
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to connect to Qdrant to create collection: %v", err)
		http.Error(w, "Failed to connect to Qdrant: "+err.Error(), http.StatusServiceUnavailable)
		return
	}
	defer respCreate.Body.Close()
	if respCreate.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(respCreate.Body)
		log.Printf("[ERROR] [debug] Qdrant collection creation failed with status %d: %s", respCreate.StatusCode, string(body))
		http.Error(w, "Failed to create Qdrant collection: "+string(body), http.StatusInternalServerError)
		return
	}
	log.Printf("[INFO] [debug] Successfully created collection '%s'", s.Collection)

	// 4. Generate embeddings from TEI concurrently using a worker pool
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

	// Start 5 concurrent embedding workers
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
				sparseVec := computeSparseVector(j.item.Text)
				results <- result{
					point: QdrantPoint{
						ID:     j.id,
						Vector: map[string]interface{}{
							"dense":  vector,
							"sparse": sparseVec,
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

	// Enqueue all items as jobs
	for i, item := range items {
		jobs <- job{id: i + 1, item: item}
	}
	close(jobs)

	// Wait for workers to finish and close results
	go func() {
		wg.Wait()
		close(results)
	}()

	// Collect points and verify no errors
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
		http.Error(w, "Seeding failed during embedding generation: "+firstErr.Error(), http.StatusInternalServerError)
		return
	}

	log.Printf("[INFO] [debug] Generated embeddings for %d points. Upserting to Qdrant...", len(points))

	// 5. Batch upsert points to Qdrant
	upsertPayload := QdrantUpsertRequest{Points: points}
	upsertBytes, err := json.Marshal(upsertPayload)
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to marshal upsert payload: %v", err)
		http.Error(w, "Failed to build Qdrant upsert payload", http.StatusInternalServerError)
		return
	}

	reqUpsert, err := http.NewRequest(http.MethodPut, s.QdrantURL+"/collections/"+s.Collection+"/points?wait=true", bytes.NewBuffer(upsertBytes))
	if err != nil {
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}
	reqUpsert.Header.Set("Content-Type", "application/json")
	respUpsert, err := client.Do(reqUpsert)
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to connect to Qdrant for upsert: %v", err)
		http.Error(w, "Failed to upsert points: "+err.Error(), http.StatusServiceUnavailable)
		return
	}
	defer respUpsert.Body.Close()

	if respUpsert.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(respUpsert.Body)
		log.Printf("[ERROR] [debug] Qdrant points upsert failed with status %d: %s", respUpsert.StatusCode, string(body))
		http.Error(w, "Failed to upsert points into Qdrant collection", http.StatusInternalServerError)
		return
	}

	log.Printf("[INFO] [debug] Database seeding completed successfully! Inserted %d points.", len(points))
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]interface{}{
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
	teiResp, err := client.Post(s.TeiURL+"/embed", "application/json", bytes.NewBuffer(teiPayload))
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

func (s *Service) IndexHandler(w http.ResponseWriter, r *http.Request) {
	if s.Environment != "dev" {
		http.Error(w, "Forbidden in non-dev environment", http.StatusForbidden)
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}

	type IndexRequest struct {
		Text string `json:"text"`
	}

	var req IndexRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid Request Body: "+err.Error(), http.StatusBadRequest)
		return
	}

	reqText := strings.TrimSpace(req.Text)
	if reqText == "" {
		http.Error(w, "Text content cannot be empty", http.StatusBadRequest)
		return
	}

	// Prepare standard payload that Indexer app expects in Stage 2 indexing matching contracts.md
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
		http.Error(w, "Failed to marshal payload", http.StatusInternalServerError)
		return
	}

	log.Printf("[INFO] [debug] Sending manual chunk payload to SQS Stage 2: %s", string(payloadBytes))

	// Form URL encoded SQS query message payload
	formData := url.Values{}
	formData.Set("Action", "SendMessage")
	formData.Set("MessageBody", string(payloadBytes))

	client := http.Client{Timeout: 5 * time.Second}
	resp, err := client.PostForm(s.SQSQueueURL, formData)
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to forward manual chunk message to SQS: %v", err)
		http.Error(w, "Failed to contact SQS Queue Service: "+err.Error(), http.StatusServiceUnavailable)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		log.Printf("[ERROR] [debug] SQS returned error code %d: %s", resp.StatusCode, string(bodyBytes))
		http.Error(w, "SQS queue returned error response", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{
		"status":  "ok",
		"message": "Manual chunk successfully sent to SQS queue. The continuous indexer worker will pull and process it in a few seconds.",
	})
}
