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

	"github.com/labstack/echo/v4"
	"github.com/maksimillian1/simple-rag/apps/api/core"
	"github.com/qdrant/fastembed-go"
	"github.com/qdrant/go-client/qdrant"
	"google.golang.org/grpc"
)

type QdrantClient interface {
	Query(ctx context.Context, in *qdrant.QueryPoints, opts ...grpc.CallOption) (*qdrant.QueryResponse, error)
}

type SparseModel interface {
	Embed(ctx context.Context, texts []string) ([]fastembed.SparseEmbedding, error)
}

type Service struct {
	QdrantURL            string
	Collection           string
	EmbeddingModelTeiURL string
	LLM                  core.LLMProvider
	DenseVectorsName     string
	SparseVectorsName    string
	SparseModel          SparseModel
	QdrantClient         QdrantClient
}

func NewService(qdrantURL, collection, embeddingModelTeiURL string, llm core.LLMProvider, denseName, sparseName string, sparseModel SparseModel, qdrantClient QdrantClient) *Service {
	return &Service{
		QdrantURL:            qdrantURL,
		Collection:           collection,
		EmbeddingModelTeiURL: embeddingModelTeiURL,
		LLM:                  llm,
		DenseVectorsName:     denseName,
		SparseVectorsName:    sparseName,
		SparseModel:          sparseModel,
		QdrantClient:         qdrantClient,
	}
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

func qdrantValueToInterface(val *qdrant.Value) interface{} {
	if val == nil {
		return nil
	}
	switch k := val.Kind.(type) {
	case *qdrant.Value_NullValue:
		return nil
	case *qdrant.Value_DoubleValue:
		return k.DoubleValue
	case *qdrant.Value_IntegerValue:
		return k.IntegerValue
	case *qdrant.Value_StringValue:
		return k.StringValue
	case *qdrant.Value_BoolValue:
		return k.BoolValue
	case *qdrant.Value_StructValue:
		if k.StructValue == nil {
			return nil
		}
		m := make(map[string]interface{})
		for key, value := range k.StructValue.Fields {
			m[key] = qdrantValueToInterface(value)
		}
		return m
	case *qdrant.Value_ListValue:
		if k.ListValue == nil {
			return nil
		}
		l := make([]interface{}, len(k.ListValue.Values))
		for idx, value := range k.ListValue.Values {
			l[idx] = qdrantValueToInterface(value)
		}
		return l
	}
	return nil
}

func payloadToMap(payload map[string]*qdrant.Value) map[string]interface{} {
	m := make(map[string]interface{})
	for k, v := range payload {
		m[k] = qdrantValueToInterface(v)
	}
	return m
}

func getPointID(id *qdrant.PointId) interface{} {
	if id == nil {
		return nil
	}
	switch opt := id.PointIdOptions.(type) {
	case *qdrant.PointId_Uuid:
		return opt.Uuid
	case *qdrant.PointId_Num:
		return opt.Num
	}
	return nil
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

func (s *Service) QueryHandler(c echo.Context) error {
	startTime := time.Now()

	ctx, cancel := context.WithTimeout(c.Request().Context(), 4500*time.Millisecond)
	defer cancel()

	var req core.QueryRequest
	if err := c.Bind(&req); err != nil {
		return c.String(http.StatusBadRequest, "invalid request body: "+err.Error())
	}

	trimmedQuery := strings.TrimSpace(req.Query)
	if len(trimmedQuery) < 3 || len(trimmedQuery) > 1000 {
		return c.String(http.StatusBadRequest, "validation error: query must be between 3 and 1000 characters")
	}

	limit := req.TopK
	if limit <= 0 {
		limit = 5
	}

	isDebug := req.Debug || c.QueryParam("debug") == "true"

	searchDense := true
	if req.Dense != nil {
		searchDense = *req.Dense
	}

	searchSparse := true
	if req.Sparse != nil {
		searchSparse = *req.Sparse
	}

	if !searchDense && !searchSparse {
		return c.String(http.StatusBadRequest, "validation error: at least one of dense or sparse search must be enabled")
	}

	var denseQueryVector []float32
	var err error
	if searchDense {
		denseQueryVector, err = s.getDenseEmbedding(ctx, trimmedQuery)
		if err != nil {
			log.Printf("[ERROR] [query] TEI embedding failed: %v", err)
			return c.String(http.StatusInternalServerError, "Embedding Generator (TEI) error: "+err.Error())
		}
	}

	var sparseEmbedding fastembed.SparseEmbedding
	if searchSparse {
		sparseEmbedding, err = s.getSparseEmbedding(ctx, trimmedQuery)
		if err != nil {
			log.Printf("[ERROR] [query] Sparse embedding failed: %v", err)
			return c.String(http.StatusInternalServerError, "Sparse embedding error: "+err.Error())
		}
	}

	poolAlpha := 0.5
	if req.PoolAlpha != nil {
		poolAlpha = *req.PoolAlpha
	}

	rrfMergePriorityAlpha := 0.5
	if req.RrfMergePriorityAlpha != nil {
		rrfMergePriorityAlpha = *req.RrfMergePriorityAlpha
	}

	rrfK := 60
	if req.RrfK > 0 {
		rrfK = req.RrfK
	}

	results, err := s.queryQdrant(ctx, denseQueryVector, sparseEmbedding, limit, poolAlpha, rrfMergePriorityAlpha, rrfK, searchDense, searchSparse)
	if err != nil {
		log.Printf("[ERROR] [query] Qdrant query failed: %v", err)
		return c.String(http.StatusInternalServerError, "Qdrant query error: "+err.Error())
	}

	citations, debugResults := buildCitationsAndDebug(results, isDebug)

	answer, err := s.LLM.GenerateAnswer(ctx, trimmedQuery, citations)
	if err != nil {
		log.Printf("[ERROR] [query] LLM answer generation failed: %v", err)
		return c.String(http.StatusInternalServerError, "Failed to generate answer from LLM: "+err.Error())
	}

	response := core.QueryResponse{
		Answer:          answer,
		ExecutionTimeMS: time.Since(startTime).Milliseconds(),
		Citations:       citations,
	}

	if isDebug {
		response.Debug = &core.DebugBlock{
			Results: debugResults,
			Count:   len(debugResults),
		}
	}

	return c.JSON(http.StatusOK, response)
}

func (s *Service) getDenseEmbedding(ctx context.Context, query string) ([]float32, error) {
	teiPayload, err := json.Marshal(map[string]string{"inputs": query})
	if err != nil {
		return nil, err
	}

	reqTei, err := http.NewRequestWithContext(ctx, http.MethodPost, s.EmbeddingModelTeiURL+"/embed", bytes.NewBuffer(teiPayload))
	if err != nil {
		return nil, err
	}
	reqTei.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	teiResp, err := client.Do(reqTei)
	if err != nil {
		return nil, fmt.Errorf("TEI unreachable: %w", err)
	}
	defer teiResp.Body.Close()

	if teiResp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(teiResp.Body)
		return nil, fmt.Errorf("TEI failed with status %d: %s", teiResp.StatusCode, string(bodyBytes))
	}

	var embedRes interface{}
	if err := json.NewDecoder(teiResp.Body).Decode(&embedRes); err != nil {
		return nil, err
	}

	return parseTEIResponse(embedRes)
}

func parseTEIResponse(embedRes interface{}) ([]float32, error) {
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
		return nil, fmt.Errorf("failed to parse generated vector from TEI")
	}

	denseQueryVector := make([]float32, len(queryVector))
	for i, v := range queryVector {
		denseQueryVector[i] = float32(v)
	}
	return denseQueryVector, nil
}

func (s *Service) getSparseEmbedding(ctx context.Context, query string) (fastembed.SparseEmbedding, error) {
	embeddings, err := s.SparseModel.Embed(ctx, []string{query})
	if err != nil {
		return fastembed.SparseEmbedding{}, err
	}
	if len(embeddings) == 0 {
		return fastembed.SparseEmbedding{}, fmt.Errorf("no sparse embeddings generated")
	}
	return embeddings[0], nil
}

func (s *Service) queryQdrant(ctx context.Context, dense []float32, sparse fastembed.SparseEmbedding, limit int, poolAlpha float64, rrfMergePriorityAlpha float64, rrfKVal int, searchDense bool, searchSparse bool) ([]*qdrant.ScoredPoint, error) {
	uint64Limit := uint64(limit)

	queryPointsReq := &qdrant.QueryPoints{
		CollectionName: s.Collection,
		Limit:          &uint64Limit,
		WithPayload: &qdrant.WithPayloadSelector{
			SelectorOptions: &qdrant.WithPayloadSelector_Enable{Enable: true},
		},
	}

	switch {
	case searchDense && searchSparse:
		totalPrefetch := float64(limit) * 4.0
		if totalPrefetch < 20 {
			totalPrefetch = 20
		}

		densePrefetchLimit := uint64(totalPrefetch * poolAlpha)
		sparsePrefetchLimit := uint64(totalPrefetch * (1.0 - poolAlpha))

		rrfK := uint32(rrfKVal)

		queryPointsReq.Prefetch = make([]*qdrant.PrefetchQuery, 0, 2)
		if densePrefetchLimit > 0 {
			queryPointsReq.Prefetch = append(queryPointsReq.Prefetch, &qdrant.PrefetchQuery{
				Query: qdrant.NewQueryDense(dense),
				Using: &s.DenseVectorsName,
				Limit: &densePrefetchLimit,
			})
		}
		if sparsePrefetchLimit > 0 {
			queryPointsReq.Prefetch = append(queryPointsReq.Prefetch, &qdrant.PrefetchQuery{
				Query: qdrant.NewQuerySparse(sparse.Indices, sparse.Values),
				Using: &s.SparseVectorsName,
				Limit: &sparsePrefetchLimit,
			})
		}
		queryPointsReq.Query = qdrant.NewQueryRRF(&qdrant.Rrf{
			K:       &rrfK,
			Weights: []float32{float32(rrfMergePriorityAlpha), float32(1.0 - rrfMergePriorityAlpha)},
		})

	case searchDense:
		queryPointsReq.Query = qdrant.NewQueryDense(dense)
		queryPointsReq.Using = &s.DenseVectorsName

	case searchSparse:
		queryPointsReq.Query = qdrant.NewQuerySparse(sparse.Indices, sparse.Values)
		queryPointsReq.Using = &s.SparseVectorsName

	default:
		return nil, fmt.Errorf("at least one search mode (dense or sparse) must be enabled")
	}

	res, err := s.QdrantClient.Query(ctx, queryPointsReq)
	if err != nil {
		return nil, fmt.Errorf("qdrant query failed: %w", err)
	}

	return res.Result, nil
}

func buildCitationsAndDebug(results []*qdrant.ScoredPoint, isDebug bool) ([]core.Citation, []core.DebugResult) {
	citations := make([]core.Citation, 0, len(results))
	debugResults := make([]core.DebugResult, 0, len(results))

	for _, point := range results {
		payloadMap := payloadToMap(point.Payload)
		fileID := getStringField(payloadMap, "file_id")
		if fileID == "" {
			fileID = "unknown"
		}
		fileName := getStringField(payloadMap, "file_name")
		if fileName == "" {
			fileName = "unknown"
		}
		
		pageNumber := getIntField(payloadMap, "page_number", 1)
		textSnippet := getContentField(payloadMap)

		citations = append(citations, core.Citation{
			DocumentID:  fileID,
			FileName:    fileName,
			PageNumber:  pageNumber,
			Score:       float64(point.Score),
			TextSnippet: textSnippet,
		})

		if isDebug {
			metadata := make(map[string]interface{})
			metadata["file_id"] = fileID
			metadata["file_name"] = fileName
			metadata["page_number"] = pageNumber
			
			if chunkIdx := getIntField(payloadMap, "chunk_index", -1); chunkIdx != -1 {
				metadata["chunk_index"] = chunkIdx
			}

			debugResults = append(debugResults, core.DebugResult{
				ID:       getPointID(point.Id),
				Score:    float64(point.Score),
				Text:     textSnippet,
				Metadata: metadata,
			})
		}
	}
	return citations, debugResults
}

func synthesizeAnswer(query string, citations []core.Citation) string {
	if len(citations) == 0 {
		return "I searched the vector database but could not find any direct references to your query. Please make sure you have successfully indexed documents or run the seeder script."
	}

	var sb strings.Builder
	sb.WriteString("Based on the retrieved document chunks, here is the synthesized answer:\n\n")

	for i, cit := range citations {
		if i >= 3 {
			break
		}
		sb.WriteString("• ")
		text := strings.TrimSpace(cit.TextSnippet)
		if len(text) > 160 {
			sb.WriteString(text[:160] + "...")
		} else {
			sb.WriteString(text)
		}
		sb.WriteString(fmt.Sprintf(" (Source: *%s*, Page %d, RRF Score: %.4f)\n", cit.FileName, cit.PageNumber, cit.Score))
	}

	return sb.String()
}
