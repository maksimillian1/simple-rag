package main

import (
	"context"
	"fmt"
	"log"
	"net/url"

	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
	"github.com/maksimillian1/simple-rag/apps/api/core"
	"github.com/maksimillian1/simple-rag/apps/api/debug"
	"github.com/maksimillian1/simple-rag/apps/api/health"
	"github.com/maksimillian1/simple-rag/apps/api/search"
	"github.com/maksimillian1/simple-rag/apps/api/ui"
	"github.com/qdrant/fastembed-go"
	"github.com/qdrant/go-client/qdrant"
)

func main() {
	cfg := core.LoadConfig()
	ctx := context.Background()

	searchService, debugService, healthService, uiService, err := bootstrapServices(ctx, cfg)
	if err != nil {
		log.Fatalf("[FATAL] Server bootstrap failed: %v", err)
	}

	e := echo.New()
	e.Use(middleware.Logger())
	e.Use(middleware.Recover())

	e.GET("/", uiService.Handler)
	e.GET("/health", healthService.Handler)
	e.POST("/api/v1/query", searchService.QueryHandler)
	e.POST("/seed", debugService.SeedHandler)
	e.POST("/index", debugService.IndexHandler)

	log.Printf("[INFO] Starting Go API on port %s...", cfg.Port)
	log.Printf("[INFO] Connected to Qdrant instance at %s", cfg.QdrantURL)
	log.Printf("[INFO] Connected to TEI service at %s", cfg.EmbeddingModelTeiURL)
	log.Printf("[INFO] Serving retrieval requests for collection '%s'", cfg.Collection)

	if err := e.Start(":" + cfg.Port); err != nil {
		log.Fatalf("[FATAL] Server failed to start: %v", err)
	}
}

func bootstrapServices(ctx context.Context, cfg core.Config) (*search.Service, *debug.Service, *health.Service, *ui.Service, error) {
	llm, err := core.NewLLMProvider(ctx, cfg.LLMProvider, cfg.AwsBedrockRegion, cfg.ModelID)
	if err != nil {
		return nil, nil, nil, nil, err
	}

	sparseModel, err := fastembed.NewSparseEmbeddingModel(fastembed.WithModel(fastembed.SPLADE_PP_ED8R))
	if err != nil {
		return nil, nil, nil, nil, fmt.Errorf("failed to init fastembed sparse model: %w", err)
	}

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
