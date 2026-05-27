package search

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
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

// SearchRequest is the payload expected by POST /search
type SearchRequest struct {
	Query  string    `json:"query"`
	Vector []float64 `json:"vector"`
	Limit  int       `json:"limit"`
}

// SearchResponse is the clean, simplified output returned to clients
type SearchResult struct {
	ID       interface{}            `json:"id"`
	Score    float64                `json:"score"`
	Text     string                 `json:"text"`
	Metadata map[string]interface{} `json:"metadata"`
}

type SearchResponse struct {
	Results []SearchResult `json:"results"`
	Count   int            `json:"count"`
}

// QdrantSearchRequest matches Qdrant's native search API format
type QdrantSearchRequest struct {
	Vector      []float64 `json:"vector"`
	Limit       int       `json:"limit"`
	WithPayload bool      `json:"with_payload"`
	WithVector  bool      `json:"with_vector"`
}

// QdrantSearchResponse matches Qdrant's native search response format
type QdrantPoint struct {
	ID      interface{}            `json:"id"`
	Score   float64                `json:"score"`
	Payload map[string]interface{} `json:"payload"`
}

type QdrantSearchResponse struct {
	Result []QdrantPoint `json:"result"`
	Status string        `json:"status"`
}

func (s *Service) Handler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}

	// Decode client request
	var req SearchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid Request Body: "+err.Error(), http.StatusBadRequest)
		return
	}

	if len(req.Vector) == 0 && req.Query == "" {
		http.Error(w, "Missing 'vector' or 'query' field", http.StatusBadRequest)
		return
	}

	if req.Limit <= 0 {
		req.Limit = 5 // Default search limit
	}

	// If text query is provided and vector is empty, call TEI to get embeddings dynamically
	if len(req.Vector) == 0 && req.Query != "" {
		log.Printf("[INFO] [search] Raw query text provided. Requesting embedding from TEI for: %q", req.Query)

		teiPayload, err := json.Marshal(map[string]string{"inputs": req.Query})
		if err != nil {
			http.Error(w, "Internal Server Error", http.StatusInternalServerError)
			return
		}

		client := http.Client{Timeout: 5 * time.Second}
		teiResp, err := client.Post(s.TeiURL+"/embed", "application/json", bytes.NewBuffer(teiPayload))
		if err != nil {
			log.Printf("[ERROR] [search] Failed to contact TEI: %v", err)
			http.Error(w, "Embedding Generator (TEI) is currently unreachable", http.StatusServiceUnavailable)
			return
		}
		defer teiResp.Body.Close()

		if teiResp.StatusCode != http.StatusOK {
			bodyBytes, _ := io.ReadAll(teiResp.Body)
			log.Printf("[ERROR] [search] TEI embedding request failed with status %d: %s", teiResp.StatusCode, string(bodyBytes))
			http.Error(w, "Embedding Generator returned error response", http.StatusInternalServerError)
			return
		}

		var embedRes interface{}
		if err := json.NewDecoder(teiResp.Body).Decode(&embedRes); err != nil {
			http.Error(w, "Failed to decode TEI response", http.StatusInternalServerError)
			return
		}

		// Parse vector out of dynamic JSON structures
		switch val := embedRes.(type) {
		case []interface{}:
			if len(val) > 0 {
				if first, ok := val[0].([]interface{}); ok {
					floats := make([]float64, len(first))
					for i, v := range first {
						floats[i], _ = v.(float64)
					}
					req.Vector = floats
				} else {
					floats := make([]float64, len(val))
					for i, v := range val {
						floats[i], _ = v.(float64)
					}
					req.Vector = floats
				}
			}
		}

		if len(req.Vector) == 0 {
			log.Printf("[ERROR] [search] Failed to parse generated vector. Response structure: %+v", embedRes)
			http.Error(w, "Failed to generate vector embedding from query text", http.StatusInternalServerError)
			return
		}
	}

	log.Printf("[INFO] [search] Querying Qdrant index (dim: %d, limit: %d)", len(req.Vector), req.Limit)

	// Prepare search request for Qdrant
	qdrantReq := QdrantSearchRequest{
		Vector:      req.Vector,
		Limit:       req.Limit,
		WithPayload: true,
		WithVector:  false,
	}

	qdrantBody, err := json.Marshal(qdrantReq)
	if err != nil {
		log.Printf("[ERROR] [search] Failed to marshal Qdrant request: %v", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}

	// Forward query to Qdrant REST API
	qdrantSearchURL := fmt.Sprintf("%s/collections/%s/points/search", s.QdrantURL, s.Collection)
	client := http.Client{Timeout: 5 * time.Second}
	qdrantResp, err := client.Post(qdrantSearchURL, "application/json", bytes.NewBuffer(qdrantBody))
	if err != nil {
		log.Printf("[ERROR] [search] Failed to contact Qdrant: %v", err)
		http.Error(w, "Failed to communicate with Vector Database", http.StatusServiceUnavailable)
		return
	}
	defer qdrantResp.Body.Close()

	if qdrantResp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(qdrantResp.Body)
		log.Printf("[ERROR] [search] Qdrant search returned status %d: %s", qdrantResp.StatusCode, string(bodyBytes))
		http.Error(w, "Vector Database returned error response", http.StatusInternalServerError)
		return
	}

	// Decode Qdrant response
	var qdrantRes QdrantSearchResponse
	if err := json.NewDecoder(qdrantResp.Body).Decode(&qdrantRes); err != nil {
		log.Printf("[ERROR] [search] Failed to decode Qdrant response: %v", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}

	// Format response
	results := make([]SearchResult, 0, len(qdrantRes.Result))
	for _, point := range qdrantRes.Result {
		textVal, _ := point.Payload["text"].(string)

		metadata := make(map[string]interface{})
		for k, v := range point.Payload {
			if k != "text" {
				metadata[k] = v
			}
		}

		results = append(results, SearchResult{
			ID:       point.ID,
			Score:    point.Score,
			Text:     textVal,
			Metadata: metadata,
		})
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(SearchResponse{
		Results: results,
		Count:   len(results),
	})
}
