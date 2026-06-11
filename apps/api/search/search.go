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

// Service encapsulates synchronous hybrid search retrieval configurations
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

// NewService instantiates a new Service with standard dependencies
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

// QueryHandler executes the built-in hybrid retrieval and LLM synthesis flow
func (s *Service) QueryHandler(w http.ResponseWriter, r *http.Request) {
	startTime := time.Now()

	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 4500*time.Millisecond)
	defer cancel()

	req, trimmedQuery, limit, err := decodeAndValidateRequest(r)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	isDebug := req.Debug || r.URL.Query().Get("debug") == "true"

	denseQueryVector, err := s.getDenseEmbedding(ctx, trimmedQuery)
	if err != nil {
		log.Printf("[ERROR] [query] TEI embedding failed: %v", err)
		http.Error(w, "Embedding Generator (TEI) error: "+err.Error(), http.StatusInternalServerError)
		return
	}

	sparseEmbedding, err := s.getSparseEmbedding(ctx, trimmedQuery)
	if err != nil {
		log.Printf("[ERROR] [query] Sparse embedding failed: %v", err)
		http.Error(w, "Sparse embedding error: "+err.Error(), http.StatusInternalServerError)
		return
	}

	results, err := s.queryQdrant(ctx, denseQueryVector, sparseEmbedding, limit)
	if err != nil {
		log.Printf("[ERROR] [query] Qdrant query failed: %v", err)
		http.Error(w, "Qdrant query error: "+err.Error(), http.StatusInternalServerError)
		return
	}

	citations, debugResults := buildCitationsAndDebug(results, isDebug)

	answer, err := s.LLM.GenerateAnswer(ctx, trimmedQuery, citations)
	if err != nil {
		log.Printf("[ERROR] [query] LLM answer generation failed: %v", err)
		http.Error(w, "Failed to generate answer from LLM: "+err.Error(), http.StatusInternalServerError)
		return
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

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}

func decodeAndValidateRequest(r *http.Request) (core.QueryRequest, string, int, error) {
	var req core.QueryRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		return req, "", 0, fmt.Errorf("invalid request body: %w", err)
	}

	trimmedQuery := strings.TrimSpace(req.Query)
	if len(trimmedQuery) < 3 || len(trimmedQuery) > 1000 {
		return req, "", 0, fmt.Errorf("validation error: query must be between 3 and 1000 characters")
	}

	limit := req.TopK
	if limit <= 0 {
		limit = 5
	}
	return req, trimmedQuery, limit, nil
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

func (s *Service) queryQdrant(ctx context.Context, dense []float32, sparse fastembed.SparseEmbedding, limit int) ([]*qdrant.ScoredPoint, error) {
	prefetchLimit := uint64(limit * 2)
	rrfK := uint32(60)
	uint64Limit := uint64(limit)

	queryPointsReq := &qdrant.QueryPoints{
		CollectionName: s.Collection,
		Prefetch: []*qdrant.PrefetchQuery{
			{
				Query: qdrant.NewQueryDense(dense),
				Using: &s.DenseVectorsName,
				Limit: &prefetchLimit,
			},
			{
				Query: qdrant.NewQuerySparse(sparse.Indices, sparse.Values),
				Using: &s.SparseVectorsName,
				Limit: &prefetchLimit,
			},
		},
		Query:       qdrant.NewQueryRRF(&qdrant.Rrf{K: &rrfK}),
		Limit:       &uint64Limit,
		WithPayload: &qdrant.WithPayloadSelector{SelectorOptions: &qdrant.WithPayloadSelector_Enable{Enable: true}},
	}

	res, err := s.QdrantClient.Query(ctx, queryPointsReq)
	if err != nil {
		return nil, err
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
