package search

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"hash/adler32"
	"io"
	"log"
	"math"
	"net/http"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/maksimillian1/simple-rag/apps/api/core"
)

// Service encapsulates synchronous hybrid search retrieval configurations
type Service struct {
	QdrantURL            string
	Collection           string
	EmbeddingModelTeiURL string
	LLM                  core.LLMProvider
	DenseVectorsName     string
	SparseVectorsName    string
}

// NewService instantiates a new Service with standard dependencies
func NewService(qdrantURL, collection, embeddingModelTeiURL string, llm core.LLMProvider, denseName, sparseName string) *Service {
	return &Service{
		QdrantURL:            qdrantURL,
		Collection:           collection,
		EmbeddingModelTeiURL: embeddingModelTeiURL,
		LLM:                  llm,
		DenseVectorsName:     denseName,
		SparseVectorsName:    sparseName,
	}
}

// SparseVector represents Qdrant sparse vector structure
type SparseVector struct {
	Indices []uint32  `json:"indices"`
	Values  []float64 `json:"values"`
}

// NamedDenseQuery represents named dense vector search payload
type NamedDenseQuery struct {
	Name   string    `json:"name"`
	Vector []float64 `json:"vector"`
}

// NamedSparseQuery represents named sparse vector search payload
type NamedSparseQuery struct {
	Name   string       `json:"name"`
	Vector SparseVector `json:"vector"`
}

// QdrantSearchRequest matches Qdrant's REST search API schema (named dense/sparse)
type QdrantSearchRequest struct {
	Vector      interface{} `json:"vector"`
	Limit       int         `json:"limit"`
	WithPayload bool        `json:"with_payload"`
	WithVector  bool        `json:"with_vector"`
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

func computeTermCountPenalty(text string, query string) float64 {
	re := regexp.MustCompile(`\b[a-zA-Z0-9]{2,}\b`)
	queryWords := re.FindAllString(strings.ToLower(query), -1)
	if len(queryWords) == 0 {
		return 1.0
	}

	textWords := re.FindAllString(strings.ToLower(text), -1)
	textCounts := make(map[string]int)
	for _, w := range textWords {
		textCounts[w]++
	}

	totalCount := 0
	for _, qw := range queryWords {
		totalCount += textCounts[qw]
	}

	if totalCount == 0 {
		return 1.0
	}

	return 1.0 / math.Log10(float64(totalCount)+10.0)
}

func getStringField(payload map[string]interface{}, key string) string {
	if val, ok := payload[key]; ok {
		if strVal, ok := val.(string); ok && strVal != "" {
			return strVal
		}
	}
	if metaVal, ok := payload["meta"]; ok {
		if metaMap, ok := metaVal.(map[string]interface{}); ok {
			if val, ok := metaMap[key]; ok {
				if strVal, ok := val.(string); ok && strVal != "" {
					return strVal
				}
			}
		}
	}
	return ""
}

func getIntField(payload map[string]interface{}, key string, defaultVal int) int {
	if val, ok := payload[key]; ok {
		switch v := val.(type) {
		case float64:
			return int(v)
		case int:
			return v
		case int32:
			return int(v)
		case int64:
			return int(v)
		}
	}
	if metaVal, ok := payload["meta"]; ok {
		if metaMap, ok := metaVal.(map[string]interface{}); ok {
			if val, ok := metaMap[key]; ok {
				switch v := val.(type) {
				case float64:
					return int(v)
				case int:
					return v
				case int32:
					return int(v)
				case int64:
					return int(v)
				}
			}
		}
	}
	return defaultVal
}

func getContentField(payload map[string]interface{}) string {
	if val := getStringField(payload, "text"); val != "" {
		return val
	}
	if val := getStringField(payload, "content"); val != "" {
		return val
	}
	return ""
}

func performRRF(densePoints, sparsePoints []QdrantPoint, k float64) []QdrantPoint {
	type rrfItem struct {
		point    QdrantPoint
		rrfScore float64
	}
	rrfMap := make(map[string]*rrfItem)

	// Process dense rank
	for rank, p := range densePoints {
		idStr := fmt.Sprintf("%v", p.ID)
		if _, exists := rrfMap[idStr]; !exists {
			rrfMap[idStr] = &rrfItem{point: p, rrfScore: 0.0}
		}
		rrfMap[idStr].rrfScore += 1.0 / (k + float64(rank+1))
	}

	// Process sparse rank
	for rank, p := range sparsePoints {
		idStr := fmt.Sprintf("%v", p.ID)
		if _, exists := rrfMap[idStr]; !exists {
			rrfMap[idStr] = &rrfItem{point: p, rrfScore: 0.0}
		}
		rrfMap[idStr].rrfScore += 1.0 / (k + float64(rank+1))
	}

	var sortedItems []*rrfItem
	for _, item := range rrfMap {
		sortedItems = append(sortedItems, item)
	}

	sort.Slice(sortedItems, func(i, j int) bool {
		return sortedItems[i].rrfScore > sortedItems[j].rrfScore
	})

	var finalPoints []QdrantPoint
	for _, item := range sortedItems {
		p := item.point
		p.Score = item.rrfScore
		finalPoints = append(finalPoints, p)
	}

	return finalPoints
}

// QdrantPoint matches Qdrant raw point payload
type QdrantPoint struct {
	ID      interface{}            `json:"id"`
	Score   float64                `json:"score"`
	Payload map[string]interface{} `json:"payload"`
}

// QdrantSearchResponse matches Qdrant query response
type QdrantSearchResponse struct {
	Result []QdrantPoint `json:"result"`
	Status string        `json:"status"`
}

// QueryHandler executes the two-stage hybrid retrieval, Reciprocal Rank Fusion, and LLM synthesis flow
func (s *Service) QueryHandler(w http.ResponseWriter, r *http.Request) {
	startTime := time.Now()

	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}

	// 1. Enforce Timeout of 4500ms using Context
	ctx, cancel := context.WithTimeout(r.Context(), 4500*time.Millisecond)
	defer cancel()

	// Decode client query request
	var req core.QueryRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid Request Body: "+err.Error(), http.StatusBadRequest)
		return
	}

	// Check if debug parameter is requested via URL query string or JSON payload
	isDebug := req.Debug || r.URL.Query().Get("debug") == "true"

	// 2. Perform Request Validation
	trimmedQuery := strings.TrimSpace(req.Query)
	if len(trimmedQuery) < 3 || len(trimmedQuery) > 1000 {
		http.Error(w, "Validation Error: query must be between 3 and 1000 characters (trimmed)", http.StatusBadRequest)
		return
	}

	limit := req.TopK
	if limit <= 0 {
		limit = 5 // Default search limit
	}

	// 3. Request dense vector embedding from TEI
	log.Printf("[INFO] [query] Requesting vector embedding from TEI for: %q", trimmedQuery)
	teiPayload, err := json.Marshal(map[string]string{"inputs": trimmedQuery})
	if err != nil {
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}

	reqTei, err := http.NewRequestWithContext(ctx, http.MethodPost, s.EmbeddingModelTeiURL+"/embed", bytes.NewBuffer(teiPayload))
	if err != nil {
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}
	reqTei.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	teiResp, err := client.Do(reqTei)
	if err != nil {
		log.Printf("[ERROR] [query] Failed to contact TEI: %v", err)
		http.Error(w, "Embedding Generator (TEI) is currently unreachable", http.StatusServiceUnavailable)
		return
	}
	defer teiResp.Body.Close()

	if teiResp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(teiResp.Body)
		log.Printf("[ERROR] [query] TEI embedding request failed with status %d: %s", teiResp.StatusCode, string(bodyBytes))
		http.Error(w, "Embedding Generator returned error response", http.StatusInternalServerError)
		return
	}

	var embedRes interface{}
	if err := json.NewDecoder(teiResp.Body).Decode(&embedRes); err != nil {
		http.Error(w, "Failed to decode TEI response", http.StatusInternalServerError)
		return
	}

	var queryVector []float64
	switch val := embedRes.(type) {
	case []interface{}:
		if len(val) > 0 {
			if first, ok := val[0].([]interface{}); ok {
				queryVector = make([]float64, len(first))
				for i, v := range first {
					queryVector[i], _ = v.(float64)
				}
			} else {
				queryVector = make([]float64, len(val))
				for i, v := range val {
					queryVector[i], _ = v.(float64)
				}
			}
		}
	}

	if len(queryVector) == 0 {
		log.Printf("[ERROR] [query] Failed to parse generated vector from TEI: %+v", embedRes)
		http.Error(w, "Failed to generate vector embedding from query text", http.StatusInternalServerError)
		return
	}

	// Calculate sparse vector for query
	querySparseVector := computeSparseVector(trimmedQuery)

	// Execute concurrent Dense and Sparse searches in Qdrant
	var wg sync.WaitGroup
	var denseResults, sparseResults []QdrantPoint
	var denseErr, sparseErr error

	qdrantSearchURL := fmt.Sprintf("%s/collections/%s/points/search", s.QdrantURL, s.Collection)

	// 1. Dense Search Routine
	wg.Add(1)
	go func() {
		defer wg.Done()
		denseReq := QdrantSearchRequest{
			Vector: NamedDenseQuery{
				Name:   s.DenseVectorsName,
				Vector: queryVector,
			},
			Limit:       limit * 2, // Query double limit for better RRF coverage
			WithPayload: true,
			WithVector:  false,
		}
		denseBody, err := json.Marshal(denseReq)
		if err != nil {
			denseErr = err
			return
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, qdrantSearchURL, bytes.NewBuffer(denseBody))
		if err != nil {
			denseErr = err
			return
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := client.Do(req)
		if err != nil {
			denseErr = err
			return
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			bodyBytes, _ := io.ReadAll(resp.Body)
			denseErr = fmt.Errorf("qdrant dense search status %d: %s", resp.StatusCode, string(bodyBytes))
			return
		}
		var searchRes QdrantSearchResponse
		if err := json.NewDecoder(resp.Body).Decode(&searchRes); err != nil {
			denseErr = err
			return
		}
		denseResults = searchRes.Result
	}()

	// 2. Sparse Search Routine
	wg.Add(1)
	go func() {
		defer wg.Done()
		sparseReq := QdrantSearchRequest{
			Vector: NamedSparseQuery{
				Name:   s.SparseVectorsName,
				Vector: querySparseVector,
			},
			Limit:       limit * 2, // Query double limit for better RRF coverage
			WithPayload: true,
			WithVector:  false,
		}
		sparseBody, err := json.Marshal(sparseReq)
		if err != nil {
			sparseErr = err
			return
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, qdrantSearchURL, bytes.NewBuffer(sparseBody))
		if err != nil {
			sparseErr = err
			return
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := client.Do(req)
		if err != nil {
			sparseErr = err
			return
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			bodyBytes, _ := io.ReadAll(resp.Body)
			sparseErr = fmt.Errorf("qdrant sparse search status %d: %s", resp.StatusCode, string(bodyBytes))
			return
		}
		var searchRes QdrantSearchResponse
		if err := json.NewDecoder(resp.Body).Decode(&searchRes); err != nil {
			sparseErr = err
			return
		}
		sparseResults = searchRes.Result
	}()

	wg.Wait()

	if denseErr != nil {
		log.Printf("[ERROR] [query] Dense search failed: %v", denseErr)
		http.Error(w, "Failed to query Dense Vector Database: "+denseErr.Error(), http.StatusInternalServerError)
		return
	}
	if sparseErr != nil {
		log.Printf("[ERROR] [query] Sparse search failed: %v", sparseErr)
		http.Error(w, "Failed to query Sparse Vector Database: "+sparseErr.Error(), http.StatusInternalServerError)
		return
	}

	// 3. Apply Word Count Penalty Algorithm to Sparse Results
	for i, p := range sparseResults {
		textSnippet := getContentField(p.Payload)
		penalty := computeTermCountPenalty(textSnippet, trimmedQuery)
		sparseResults[i].Score = p.Score * penalty
	}

	// Re-sort sparse results based on penalized scores
	sort.Slice(sparseResults, func(i, j int) bool {
		return sparseResults[i].Score > sparseResults[j].Score
	})

	// 4. Merge dense & sparse results via Reciprocal Rank Fusion (RRF with k=60)
	rrfPoints := performRRF(denseResults, sparseResults, 60.0)

	// Slice down to top_k limit
	if len(rrfPoints) > limit {
		rrfPoints = rrfPoints[:limit]
	}

	// Convert RRF points to final QdrantSearchResponse schema for compatibility
	var qdrantRes QdrantSearchResponse
	qdrantRes.Result = rrfPoints
	qdrantRes.Status = "ok"

	// 5. Structure Citations and Debug blocks
	citations := make([]core.Citation, 0, len(qdrantRes.Result))
	debugResults := make([]core.DebugResult, 0, len(qdrantRes.Result))

	for _, point := range qdrantRes.Result {
		// Parse structured fields from point payload
		fileID := getStringField(point.Payload, "file_id")
		if fileID == "" {
			fileID = "unknown"
		}
		fileName := getStringField(point.Payload, "file_name")
		if fileName == "" {
			fileName = "unknown"
		}
		
		pageNumber := getIntField(point.Payload, "page_number", 1)
		textSnippet := getContentField(point.Payload)

		citations = append(citations, core.Citation{
			DocumentID:  fileID,
			FileName:    fileName,
			PageNumber:  pageNumber,
			Score:       point.Score,
			TextSnippet: textSnippet,
		})

		if isDebug {
			// Backwards compatibility metadata mapping for the dashboard rendering
			metadata := make(map[string]interface{})
			metadata["file_id"] = fileID
			metadata["file_name"] = fileName
			metadata["page_number"] = pageNumber
			
			if chunkIdx := getIntField(point.Payload, "chunk_index", -1); chunkIdx != -1 {
				metadata["chunk_index"] = chunkIdx
			}

			debugResults = append(debugResults, core.DebugResult{
				ID:       point.ID,
				Score:    point.Score,
				Text:     textSnippet,
				Metadata: metadata,
			})
		}
	}

	// 6. Synthesize RAG Answer
	answer, err := s.LLM.GenerateAnswer(ctx, trimmedQuery, citations)
	if err != nil {
		log.Printf("[ERROR] [query] LLM answer generation failed: %v", err)
		http.Error(w, "Failed to generate answer from LLM: "+err.Error(), http.StatusInternalServerError)
		return
	}

	duration := time.Since(startTime).Milliseconds()

	response := core.QueryResponse{
		Answer:          answer,
		ExecutionTimeMS: duration,
		Citations:       citations,
	}

	if isDebug {
		response.Debug = &core.DebugBlock{
			Results: debugResults,
			Count:   len(debugResults),
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}

func synthesizeAnswer(query string, citations []core.Citation) string {
	if len(citations) == 0 {
		return "I searched the vector database but could not find any direct references to your query. Please make sure you have successfully indexed documents or run the seeder script."
	}

	var sb strings.Builder
	sb.WriteString("Based on the retrieved document chunks, here is the synthesized answer:\n\n")

	// Create cohesive bullet points from matching chunks
	for i, cit := range citations {
		if i >= 3 {
			break // Only summarize top-3
		}
		sb.WriteString("• ")
		text := strings.TrimSpace(cit.TextSnippet)
		if len(text) > 160 {
			sb.WriteString(text[:160] + "...")
		} else {
			sb.WriteString(text)
		}
		sb.WriteString(fmt.Sprintf(" (Source: *%s*, Page %d, Similarity: %.1f%%)\n", cit.FileName, cit.PageNumber, cit.Score*100))
	}

	return sb.String()
}
