package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"
)

// Config holds environment configurations
type Config struct {
	Port       string
	QdrantURL  string
	Collection string
}

// SearchRequest is the payload expected by POST /search
type SearchRequest struct {
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

func main() {
	// Parse configurations with sensible defaults
	cfg := Config{
		Port:       getEnv("PORT", "8080"),
		QdrantURL:  getEnv("QDRANT_URL", "http://localhost:6333"),
		Collection: getEnv("COLLECTION_NAME", "demo_collection"),
	}

	mux := http.NewServeMux()

	// 1. Health & Connection Endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		// Perform deep health check by querying Qdrant's readyz endpoint
		client := http.Client{Timeout: 3 * time.Second}
		resp, err := client.Get(cfg.QdrantURL + "/readyz")
		if err != nil {
			log.Printf("[ERROR] Health check failed to connect to Qdrant: %v", err)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			json.NewEncoder(w).Encode(map[string]string{
				"status":        "error",
				"qdrant_status": "disconnected",
				"details":       err.Error(),
			})
			return
		}
		defer resp.Body.Close()

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{
			"status":        "ok",
			"qdrant_status": "connected",
			"message":       "Go API and Qdrant are fully operational",
		})
	})

	// 2. Query / Search Endpoint
	mux.HandleFunc("/search", func(w http.ResponseWriter, r *http.Request) {
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

		if len(req.Vector) == 0 {
			http.Error(w, "Missing or empty 'vector' field", http.StatusBadRequest)
			return
		}

		if req.Limit <= 0 {
			req.Limit = 3 // Default search limit
		}

		log.Printf("[INFO] Received search request (dim: %d, limit: %d)", len(req.Vector), req.Limit)

		// Prepare search request for Qdrant
		qdrantReq := QdrantSearchRequest{
			Vector:      req.Vector,
			Limit:       req.Limit,
			WithPayload: true,
			WithVector:  false,
		}

		qdrantBody, err := json.Marshal(qdrantReq)
		if err != nil {
			log.Printf("[ERROR] Failed to marshal Qdrant request: %v", err)
			http.Error(w, "Internal Server Error", http.StatusInternalServerError)
			return
		}

		// Forward query to Qdrant REST API
		qdrantSearchURL := fmt.Sprintf("%s/collections/%s/points/search", cfg.QdrantURL, cfg.Collection)
		client := http.Client{Timeout: 5 * time.Second}
		qdrantResp, err := client.Post(qdrantSearchURL, "application/json", bytes.NewBuffer(qdrantBody))
		if err != nil {
			log.Printf("[ERROR] Failed to contact Qdrant: %v", err)
			http.Error(w, "Failed to communicate with Vector Database", http.StatusServiceUnavailable)
			return
		}
		defer qdrantResp.Body.Close()

		if qdrantResp.StatusCode != http.StatusOK {
			bodyBytes, _ := io.ReadAll(qdrantResp.Body)
			log.Printf("[ERROR] Qdrant search returned status %d: %s", qdrantResp.StatusCode, string(bodyBytes))
			http.Error(w, "Vector Database returned error response", http.StatusInternalServerError)
			return
		}

		// Decode Qdrant response
		var qdrantRes QdrantSearchResponse
		if err := json.NewDecoder(qdrantResp.Body).Decode(&qdrantRes); err != nil {
			log.Printf("[ERROR] Failed to decode Qdrant response: %v", err)
			http.Error(w, "Internal Server Error", http.StatusInternalServerError)
			return
		}

		// Format and simplify response for client
		results := make([]SearchResult, 0, len(qdrantRes.Result))
		for _, point := range qdrantRes.Result {
			// Extract primary 'text' from payload, keeping remaining payload fields as metadata
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

		// Return JSON response to client
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(SearchResponse{
			Results: results,
			Count:   len(results),
		})
	})

	log.Printf("[INFO] Starting lightweight Go API on port %s...", cfg.Port)
	log.Printf("[INFO] Connected to Qdrant instance at %s", cfg.QdrantURL)
	log.Printf("[INFO] Serving retrieval requests for collection '%s'", cfg.Collection)

	if err := http.ListenAndServe(":"+cfg.Port, mux); err != nil {
		log.Fatalf("[FATAL] Server failed: %v", err)
	}
}

func getEnv(key, defaultVal string) string {
	if val, exists := os.LookupEnv(key); exists {
		return val
	}
	return defaultVal
}
