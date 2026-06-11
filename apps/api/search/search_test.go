package search

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/maksimillian1/simple-rag/apps/api/core"
	"github.com/qdrant/fastembed-go"
	"github.com/qdrant/go-client/qdrant"
	"google.golang.org/grpc"
)

type mockQdrantClient struct {
	t               *testing.T
	expectedDense   []float32
	expectedSparse  []float32
	expectedIndices []uint32
}

func (m *mockQdrantClient) Search(ctx context.Context, in *qdrant.SearchPoints, opts ...grpc.CallOption) (*qdrant.SearchResponse, error) {
	if in.CollectionName != "test_collection" {
		m.t.Errorf("expected collection 'test_collection', got %s", in.CollectionName)
	}

	if *in.VectorName == "text-dense" {
		if len(in.Vector) != len(m.expectedDense) {
			m.t.Errorf("dense vector length mismatch: expected %d, got %d", len(m.expectedDense), len(in.Vector))
		}
		for i, val := range m.expectedDense {
			if in.Vector[i] != val {
				m.t.Errorf("dense vector mismatch at %d", i)
			}
		}
	} else if *in.VectorName == "text-sparse" {
		if in.SparseIndices == nil {
			m.t.Errorf("sparse indices must not be nil")
		}
		if len(in.Vector) != len(m.expectedSparse) {
			m.t.Errorf("sparse values length mismatch: expected %d, got %d", len(m.expectedSparse), len(in.Vector))
		}
		if len(in.SparseIndices.Data) != len(m.expectedIndices) {
			m.t.Errorf("sparse indices length mismatch: expected %d, got %d", len(m.expectedIndices), len(in.SparseIndices.Data))
		}
	} else {
		m.t.Errorf("unexpected vector name: %s", *in.VectorName)
	}

	valString := &qdrant.Value{Kind: &qdrant.Value_StringValue{StringValue: "test content"}}
	valPage := &qdrant.Value{Kind: &qdrant.Value_DoubleValue{DoubleValue: 1.0}}
	
	return &qdrant.SearchResponse{
		Result: []*qdrant.ScoredPoint{
			{
				Id: qdrant.NewIDUUID("cc4a0c2e-73c3-5486-afc6-9fbbb1051eb6"),
				Score: 0.85,
				Payload: map[string]*qdrant.Value{
					"content":     valString,
					"file_id":     &qdrant.Value{Kind: &qdrant.Value_StringValue{StringValue: "doc_1"}},
					"file_name":   &qdrant.Value{Kind: &qdrant.Value_StringValue{StringValue: "test.pdf"}},
					"page_number": valPage,
				},
			},
		},
	}, nil
}

type mockSparseModel struct {
	expectedQuery string
	result        fastembed.SparseEmbedding
}

func (m *mockSparseModel) Embed(ctx context.Context, texts []string) ([]fastembed.SparseEmbedding, error) {
	if len(texts) == 0 || texts[0] != m.expectedQuery {
		return nil, fmt.Errorf("unexpected query for sparse embedder: %v", texts)
	}
	return []fastembed.SparseEmbedding{m.result}, nil
}

func TestQueryHandler_SparseDenseHybridSearch(t *testing.T) {
	denseVec := []float32{0.1, 0.2, 0.3}
	sparseVec := fastembed.SparseEmbedding{
		Indices: []uint32{100, 200},
		Values:  []float32{0.5, 0.8},
	}

	qClient := &mockQdrantClient{
		t:               t,
		expectedDense:   denseVec,
		expectedSparse:  sparseVec.Values,
		expectedIndices: sparseVec.Indices,
	}

	sModel := &mockSparseModel{
		expectedQuery: "test query",
		result:        sparseVec,
	}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode([]float64{0.1, 0.2, 0.3})
	}))
	defer ts.Close()

	mockLLM := core.NewMockProvider()

	svc := NewService(
		"http://localhost:6333",
		"test_collection",
		ts.URL,
		mockLLM,
		"text-dense",
		"text-sparse",
		sModel,
		qClient,
	)

	queryReq := core.QueryRequest{
		Query: "test query",
		TopK:  3,
	}
	reqBody, _ := json.Marshal(queryReq)
	req := httptest.NewRequest("POST", "/api/v1/query", bytes.NewBuffer(reqBody))
	w := httptest.NewRecorder()

	svc.QueryHandler(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("expected status 200, got %d: %s", resp.StatusCode, string(body))
	}

	var queryResp core.QueryResponse
	if err := json.NewDecoder(resp.Body).Decode(&queryResp); err != nil {
		t.Fatalf("failed to decode query response: %v", err)
	}

	if len(queryResp.Citations) != 1 {
		t.Fatalf("expected 1 citation, got %d", len(queryResp.Citations))
	}
	if queryResp.Citations[0].FileName != "test.pdf" {
		t.Errorf("expected citation file name 'test.pdf', got '%s'", queryResp.Citations[0].FileName)
	}
	if queryResp.Citations[0].TextSnippet != "test content" {
		t.Errorf("expected text snippet 'test content', got '%s'", queryResp.Citations[0].TextSnippet)
	}
}

func TestComputeTermCountPenalty(t *testing.T) {
	penaltyNoMatch := computeTermCountPenalty("Financial statement text", "growth")
	if penaltyNoMatch != 1.0 {
		t.Errorf("expected penalty to be 1.0 for no matching query words, got %f", penaltyNoMatch)
	}

	penaltyOneMatch := computeTermCountPenalty("Financial growth text", "growth")
	expectedOne := 1.0 / math.Log10(11.0)
	if math.Abs(penaltyOneMatch-expectedOne) > 1e-6 {
		t.Errorf("expected penalty %f, got %f", expectedOne, penaltyOneMatch)
	}

	penaltyThreeMatches := computeTermCountPenalty("growth growth financial growth text", "growth")
	expectedThree := 1.0 / math.Log10(13.0)
	if math.Abs(penaltyThreeMatches-expectedThree) > 1e-6 {
		t.Errorf("expected penalty %f, got %f", expectedThree, penaltyThreeMatches)
	}

	penaltyMulti := computeTermCountPenalty("growth audit audit document", "growth audit")
	if math.Abs(penaltyMulti-expectedThree) > 1e-6 {
		t.Errorf("expected penalty %f, got %f", expectedThree, penaltyMulti)
	}
}

func TestPerformRRF(t *testing.T) {
	densePoints := []QdrantPoint{
		{ID: "point_A", Score: 0.95, Payload: map[string]interface{}{"text": "A"}},
		{ID: "point_B", Score: 0.90, Payload: map[string]interface{}{"text": "B"}},
	}

	sparsePoints := []QdrantPoint{
		{ID: "point_B", Score: 0.85, Payload: map[string]interface{}{"text": "B"}},
		{ID: "point_C", Score: 0.80, Payload: map[string]interface{}{"text": "C"}},
	}

	results := performRRF(densePoints, sparsePoints, 60.0)

	if len(results) != 3 {
		t.Fatalf("expected 3 merged points, got %d", len(results))
	}

	if results[0].ID != "point_B" {
		t.Errorf("expected top point to be point_B, got %v", results[0].ID)
	}
	expectedB := 1.0/62.0 + 1.0/61.0
	if math.Abs(results[0].Score-expectedB) > 1e-6 {
		t.Errorf("expected Point B score %f, got %f", expectedB, results[0].Score)
	}

	if results[1].ID != "point_A" {
		t.Errorf("expected second point to be point_A, got %v", results[1].ID)
	}
	expectedA := 1.0 / 61.0
	if math.Abs(results[1].Score-expectedA) > 1e-6 {
		t.Errorf("expected Point A score %f, got %f", expectedA, results[1].Score)
	}

	if results[2].ID != "point_C" {
		t.Errorf("expected third point to be point_C, got %v", results[2].ID)
	}
	expectedC := 1.0 / 62.0
	if math.Abs(results[2].Score-expectedC) > 1e-6 {
		t.Errorf("expected Point C score %f, got %f", expectedC, results[2].Score)
	}
}

func TestMockProvider(t *testing.T) {
	mock := core.NewMockProvider()
	citations := []core.Citation{
		{
			DocumentID:  "doc_1",
			FileName:    "test.pdf",
			PageNumber:  2,
			Score:       0.85,
			TextSnippet: "Optimized infrastructure via spot instances.",
		},
	}
	ans, err := mock.GenerateAnswer(context.Background(), "cost optimization", citations)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(ans, "test.pdf") || !strings.Contains(ans, "Optimized infrastructure") {
		t.Errorf("expected answer to contain citations and snippet, got: %q", ans)
	}
}

func TestBedrockProvider_FallbackWhenModelIDEmpty(t *testing.T) {
	provider, err := core.NewBedrockProvider(context.Background(), "us-east-1", "")
	if err != nil {
		t.Fatalf("failed to create bedrock provider: %v", err)
	}

	citations := []core.Citation{
		{
			DocumentID:  "doc_1",
			FileName:    "test.pdf",
			PageNumber:  2,
			Score:       0.85,
			TextSnippet: "Optimized infrastructure via spot instances.",
		},
	}
	ans, err := provider.GenerateAnswer(context.Background(), "cost optimization", citations)
	if err != nil {
		t.Fatalf("unexpected error invoking provider: %v", err)
	}

	if !strings.Contains(ans, "test.pdf") || !strings.Contains(ans, "Optimized infrastructure") {
		t.Errorf("expected fallback answer to contain citations and snippet, got: %q", ans)
	}
}
