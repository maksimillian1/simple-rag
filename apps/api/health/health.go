package health

import (
	"log"
	"net/http"
	"time"

	"github.com/labstack/echo/v4"
)

type Service struct {
	QdrantURL            string
	EmbeddingModelTeiURL string
	Environment          string
	Collection           string
}

func NewService(qdrantURL, embeddingModelTeiURL, environment, collection string) *Service {
	return &Service{
		QdrantURL:            qdrantURL,
		EmbeddingModelTeiURL: embeddingModelTeiURL,
		Environment:          environment,
		Collection:           collection,
	}
}

func (s *Service) Handler(c echo.Context) error {
	client := http.Client{Timeout: 3 * time.Second}

	qdrantStatus := "connected"
	resp, err := client.Get(s.QdrantURL + "/readyz")
	if err != nil {
		qdrantStatus = "disconnected"
		log.Printf("[ERROR] Health check failed to connect to Qdrant at %s: %v", s.QdrantURL, err)
	} else {
		resp.Body.Close()
	}

	teiStatus := "connected"
	teiResp, err := client.Get(s.EmbeddingModelTeiURL + "/health")
	if err != nil {
		teiStatus = "disconnected"
		log.Printf("[ERROR] Health check failed to connect to TEI embeddings at %s: %v", s.EmbeddingModelTeiURL, err)
	} else {
		teiResp.Body.Close()
	}

	status := http.StatusOK
	if qdrantStatus == "disconnected" || teiStatus == "disconnected" {
		status = http.StatusServiceUnavailable
	}

	return c.JSON(status, map[string]interface{}{
		"status":        "ok",
		"qdrant_status": qdrantStatus,
		"tei_status":    teiStatus,
		"environment":   s.Environment,
		"collection":    s.Collection,
	})
}
