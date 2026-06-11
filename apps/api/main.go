package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"net/url"

	"github.com/maksimillian1/simple-rag/apps/api/core"
	"github.com/maksimillian1/simple-rag/apps/api/debug"
	"github.com/maksimillian1/simple-rag/apps/api/health"
	"github.com/maksimillian1/simple-rag/apps/api/search"
	"github.com/maksimillian1/simple-rag/apps/api/ui"
	"github.com/qdrant/fastembed-go"
	"github.com/qdrant/go-client/qdrant"
)

func main() {
	// 1. Initialize environment configurations in a single, cohesive call
	cfg := core.LoadConfig()

	ctx := context.Background()

	// 2. Bootstrap application services and core dependencies
	searchService, debugService, healthService, uiService, err := bootstrapServices(ctx, cfg)
	if err != nil {
		log.Fatalf("[FATAL] Server bootstrap failed: %v", err)
	}

	// 3. Register descriptive route endpoints
	mux := http.NewServeMux()

	// Root UI Dashboard Handler
	mux.HandleFunc("/", uiService.Handler)

	// Deep Health check handler checking Qdrant & TEI status
	mux.HandleFunc("/health", healthService.Handler)

	// Search & Generation Hybrid Query Endpoint
	mux.HandleFunc("/api/v1/query", searchService.QueryHandler)

	// Development database seed endpoint
	mux.HandleFunc("/seed", debugService.SeedHandler)

	// Development manual chunk index endpoint
	mux.HandleFunc("/index", debugService.IndexHandler)

	log.Printf("[INFO] Starting Go API on port %s...", cfg.Port)
	log.Printf("[INFO] Connected to Qdrant instance at %s", cfg.QdrantURL)
	log.Printf("[INFO] Connected to TEI service at %s", cfg.EmbeddingModelTeiURL)
	log.Printf("[INFO] Serving retrieval requests for collection '%s'", cfg.Collection)

	if err := http.ListenAndServe(":"+cfg.Port, mux); err != nil {
		log.Fatalf("[FATAL] Server failed to start: %v", err)
	}
}

// bootstrapServices initializes all core service providers, adapters, and modular handlers
func bootstrapServices(ctx context.Context, cfg core.Config) (*search.Service, *debug.Service, *health.Service, *ui.Service, error) {
	// Initialize Llama LLM Provider via Bedrock Runtime or mock fallback
	llm, err := core.NewLLMProvider(ctx, cfg.LLMProvider, cfg.AwsRegion, cfg.ModelID)
	if err != nil {
		return nil, nil, nil, nil, err
	}

	// Initialize fastembed sparse model
	sparseModel, err := fastembed.NewSparseEmbeddingModel(fastembed.WithModel(fastembed.SPLADE_PP_ED8R))
	if err != nil {
		return nil, nil, nil, nil, fmt.Errorf("failed to init fastembed sparse model: %w", err)
	}

	// Parse host for Qdrant gRPC client
	host := "localhost"
	if u, err := url.Parse(cfg.QdrantURL); err == nil && u.Hostname() != "" {
		host = u.Hostname()
	}

	qClient, err := qdrant.NewClient(&qdrant.Config{
		Host: host,
		Port: 6334,
	})
	if err != nil {
		return nil, nil, nil, nil, fmt.Errorf("failed to connect to Qdrant gRPC: %w", err)
	}

	searchService := search.NewService(cfg.QdrantURL, cfg.Collection, cfg.EmbeddingModelTeiURL, llm, cfg.DenseVectorsName, cfg.SparseVectorsName, sparseModel, qClient.GetPointsClient())
	debugService := debug.NewService(cfg.Environment, cfg.SQSQueueURL, cfg.QdrantURL, cfg.EmbeddingModelTeiURL, cfg.Collection, cfg.DenseVectorsName, cfg.SparseVectorsName, qClient, sparseModel)
	healthService := health.NewService(cfg.QdrantURL, cfg.EmbeddingModelTeiURL, cfg.Environment, cfg.Collection)
	uiService := ui.NewService(cfg.Environment, cfg.Collection)

	return searchService, debugService, healthService, uiService, nil
}
