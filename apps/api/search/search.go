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
)

type Service struct {
	QdrantURL  string
	Collection string
	TeiURL     string
}

func NewService(qdrantURL, collection, teiURL string) *Service {
	return &Service{
		QdrantURL:  qdrantURL,
		Collection: collection,
		TeiURL:     teiURL,
	}
}

// QueryRequest conforms to the POST /api/v1/query contract in contracts.md
type QueryRequest struct {
	Query string  `json:"query"`
	TopK  int     `json:"top_k"`
	Alpha float64 `json:"alpha"`
	Debug bool    `json:"debug"` // Supports JSON body option for debug
}

// Citation conforms to the POST /api/v1/query response structure in contracts.md
type Citation struct {
	DocumentID  string  `json:"document_id"`
	FileName    string  `json:"file_name"`
	PageNumber  int     `json:"page_number"`
	Score       float64 `json:"score"`
	TextSnippet string  `json:"text_snippet"`
}

// DebugResult maps to the old /search results format for seamless dashboard rendering
type DebugResult struct {
	ID       interface{}            `json:"id"`
	Score    float64                `json:"score"`
	Text     string                 `json:"text"`
	Metadata map[string]interface{} `json:"metadata"`
}

type DebugBlock struct {
	Results []DebugResult `json:"results"`
	Count   int           `json:"count"`
}

// QueryResponse conforms to the POST /api/v1/query response structure in contracts.md
type QueryResponse struct {
	Answer          string      `json:"answer"`
	ExecutionTimeMS int64       `json:"execution_time_ms"`
	Citations       []Citation  `json:"citations"`
	Debug           *DebugBlock `json:"debug,omitempty"`
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

type QdrantPoint struct {
	ID      interface{}            `json:"id"`
	Score   float64                `json:"score"`
	Payload map[string]interface{} `json:"payload"`
}

type QdrantSearchResponse struct {
	Result []QdrantPoint `json:"result"`
	Status string        `json:"status"`
}

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
	var req QueryRequest
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

	reqTei, err := http.NewRequestWithContext(ctx, http.MethodPost, s.TeiURL+"/embed", bytes.NewBuffer(teiPayload))
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
				Name:   "dense",
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
				Name:   "sparse",
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
		textSnippet, _ := p.Payload["text"].(string)
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
	citations := make([]Citation, 0, len(qdrantRes.Result))
	debugResults := make([]DebugResult, 0, len(qdrantRes.Result))

	for _, point := range qdrantRes.Result {
		// Parse structured fields from point payload
		fileID, _ := point.Payload["file_id"].(string)
		if fileID == "" {
			fileID = "unknown"
		}
		fileName, _ := point.Payload["file_name"].(string)
		if fileName == "" {
			fileName = "unknown"
		}
		
		// page_number might be decoded as float64 from JSON
		pageNumber := 1
		if pVal, ok := point.Payload["page_number"]; ok {
			if fVal, ok := pVal.(float64); ok {
				pageNumber = int(fVal)
			}
		}

		textSnippet, _ := point.Payload["text"].(string)

		citations = append(citations, Citation{
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
			
			if chunkIdxVal, ok := point.Payload["chunk_index"]; ok {
				if fIdx, ok := chunkIdxVal.(float64); ok {
					metadata["chunk_index"] = int(fIdx)
				}
			}

			debugResults = append(debugResults, DebugResult{
				ID:       point.ID,
				Score:    point.Score,
				Text:     textSnippet,
				Metadata: metadata,
			})
		}
	}

	// 6. Synthesize RAG Answer
	answer := synthesizeAnswer(trimmedQuery, citations)

	duration := time.Since(startTime).Milliseconds()

	response := QueryResponse{
		Answer:          answer,
		ExecutionTimeMS: duration,
		Citations:       citations,
	}

	if isDebug {
		response.Debug = &DebugBlock{
			Results: debugResults,
			Count:   len(debugResults),
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}

func synthesizeAnswer(query string, citations []Citation) string {
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
