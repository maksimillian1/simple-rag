package main

import (
	"context"
	_ "embed"
	"encoding/json"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/maksimillian1/simple-rag/apps/api/core"
	"github.com/maksimillian1/simple-rag/apps/api/debug"
	"github.com/maksimillian1/simple-rag/apps/api/search"
)

//go:embed templates/index.html
var indexHTML string

func main() {
	// Attempt to load .env locally before reading environment configurations
	core.LoadEnv()

	// Parse configurations with sensible defaults
	cfg := core.Config{
		Port:        core.GetEnv("PORT", "8080"),
		QdrantURL:   core.GetEnv("QDRANT_URL", "http://localhost:6333"),
		Collection:  core.GetEnv("COLLECTION_NAME", "demo_collection"),
		TeiURL:      core.GetEnv("TEI_URL", "http://localhost:8081"),
		Environment: core.GetEnv("ENVIRONMENT", "production"),
		SQSQueueURL: core.GetEnv("AWS_SQS_STAGE_2_URL", "http://localhost:9324/000000000000/stage-2-indexing"),
		LLMProvider: core.GetEnv("LLM_PROVIDER", "mock"),
		AwsRegion:   core.GetEnv("AWS_DEFAULT_REGION", "us-east-1"),
		ModelID:     core.GetEnv("MODEL_ID", ""),
	}

	ctx := context.Background()
	llm, err := search.NewLLMProvider(ctx, cfg.LLMProvider, cfg.AwsRegion, cfg.ModelID)
	if err != nil {
		log.Fatalf("[FATAL] Failed to initialize LLM provider: %v", err)
	}

	// Initialize modular services
	searchService := search.NewService(cfg.QdrantURL, cfg.Collection, cfg.TeiURL, llm)
	debugService := debug.NewService(cfg.Environment, cfg.SQSQueueURL, cfg.QdrantURL, cfg.TeiURL, cfg.Collection)

	mux := http.NewServeMux()

	// 1. Root / UI Dashboard Handler
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		html := strings.Replace(indexHTML, "{{.Environment}}", cfg.Environment, -1)
		html = strings.Replace(html, "{{.Collection}}", cfg.Collection, -1)
		w.Write([]byte(html))
	})

	// 2. Health & Connection Endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		// Perform deep health check by querying Qdrant's readyz endpoint
		client := http.Client{Timeout: 3 * time.Second}
		resp, err := client.Get(cfg.QdrantURL + "/readyz")
		qdrantStatus := "connected"
		if err != nil {
			qdrantStatus = "disconnected"
			log.Printf("[ERROR] Health check failed to connect to Qdrant: %v", err)
		} else {
			resp.Body.Close()
		}

		// Query TEI's health endpoint as well
		teiStatus := "connected"
		teiResp, err := client.Get(cfg.TeiURL + "/health")
		if err != nil {
			teiStatus = "disconnected"
			log.Printf("[ERROR] Health check failed to connect to TEI: %v", err)
		} else {
			teiResp.Body.Close()
		}

		w.Header().Set("Content-Type", "application/json")
		if qdrantStatus == "disconnected" || teiStatus == "disconnected" {
			w.WriteHeader(http.StatusServiceUnavailable)
		} else {
			w.WriteHeader(http.StatusOK)
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"status":        "ok",
			"qdrant_status": qdrantStatus,
			"tei_status":    teiStatus,
			"environment":   cfg.Environment,
			"collection":    cfg.Collection,
		})
	})

	// 3. New Production Query Endpoint
	mux.HandleFunc("/api/v1/query", searchService.QueryHandler)

	// 4. Modular Debug Seeder Endpoint
	mux.HandleFunc("/seed", debugService.SeedHandler)

	// 5. Modular Debug Ingestion Index Endpoint
	mux.HandleFunc("/index", debugService.IndexHandler)

	log.Printf("[INFO] Starting lightweight Go API on port %s...", cfg.Port)
	log.Printf("[INFO] Connected to Qdrant instance at %s", cfg.QdrantURL)
	log.Printf("[INFO] Connected to TEI service at %s", cfg.TeiURL)
	log.Printf("[INFO] Serving retrieval requests for collection '%s'", cfg.Collection)

	if err := http.ListenAndServe(":"+cfg.Port, mux); err != nil {
		log.Fatalf("[FATAL] Server failed: %v", err)
	}
}
