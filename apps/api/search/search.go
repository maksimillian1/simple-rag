package search

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
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

// QdrantSearchRequest matches Qdrant's REST search API schema
type QdrantSearchRequest struct {
	Vector      []float64 `json:"vector"`
	Limit       int       `json:"limit"`
	WithPayload bool      `json:"with_payload"`
	WithVector  bool      `json:"with_vector"`
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

	// 4. Query Qdrant REST API
	log.Printf("[INFO] [query] Searching Qdrant collection '%s' (limit: %d)", s.Collection, limit)
	qdrantReq := QdrantSearchRequest{
		Vector:      queryVector,
		Limit:       limit,
		WithPayload: true,
		WithVector:  false,
	}

	qdrantBody, err := json.Marshal(qdrantReq)
	if err != nil {
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}

	qdrantSearchURL := fmt.Sprintf("%s/collections/%s/points/search", s.QdrantURL, s.Collection)
	reqQdrant, err := http.NewRequestWithContext(ctx, http.MethodPost, qdrantSearchURL, bytes.NewBuffer(qdrantBody))
	if err != nil {
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}
	reqQdrant.Header.Set("Content-Type", "application/json")

	qdrantResp, err := client.Do(reqQdrant)
	if err != nil {
		log.Printf("[ERROR] [query] Failed to contact Qdrant: %v", err)
		http.Error(w, "Failed to communicate with Vector Database", http.StatusServiceUnavailable)
		return
	}
	defer qdrantResp.Body.Close()

	if qdrantResp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(qdrantResp.Body)
		log.Printf("[ERROR] [query] Qdrant search returned status %d: %s", qdrantResp.StatusCode, string(bodyBytes))
		http.Error(w, "Vector Database returned error response", http.StatusInternalServerError)
		return
	}

	var qdrantRes QdrantSearchResponse
	if err := json.NewDecoder(qdrantResp.Body).Decode(&qdrantRes); err != nil {
		log.Printf("[ERROR] [query] Failed to decode Qdrant response: %v", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}

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
