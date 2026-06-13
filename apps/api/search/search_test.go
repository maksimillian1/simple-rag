package search

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/labstack/echo/v4"
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

func (m *mockQdrantClient) Query(ctx context.Context, in *qdrant.QueryPoints, opts ...grpc.CallOption) (*qdrant.QueryResponse, error) {
	if in.CollectionName != "test_collection" {
		m.t.Errorf("expected collection 'test_collection', got %s", in.CollectionName)
	}

	if len(in.Prefetch) != 2 {
		m.t.Errorf("expected 2 prefetch queries, got %d", len(in.Prefetch))
	}

	// Verify dense prefetch query
	densePrefetch := in.Prefetch[0]
	if *densePrefetch.Using != "text-dense" {
		m.t.Errorf("expected dense prefetch to use 'text-dense', got %s", *densePrefetch.Using)
	}
	if densePrefetch.Query == nil || densePrefetch.Query.GetNearest() == nil || densePrefetch.Query.GetNearest().GetDense() == nil {
		m.t.Errorf("dense prefetch query must not be nil and have dense nearest vector input")
	} else {
		denseVec := densePrefetch.Query.GetNearest().GetDense().GetData()
		if len(denseVec) != len(m.expectedDense) {
			m.t.Errorf("dense vector length mismatch: expected %d, got %d", len(m.expectedDense), len(denseVec))
		}
		for i, val := range m.expectedDense {
			if denseVec[i] != val {
				m.t.Errorf("dense vector mismatch at %d", i)
			}
		}
	}

	// Verify sparse prefetch query
	sparsePrefetch := in.Prefetch[1]
	if *sparsePrefetch.Using != "text-sparse" {
		m.t.Errorf("expected sparse prefetch to use 'text-sparse', got %s", *sparsePrefetch.Using)
	}
	if sparsePrefetch.Query == nil || sparsePrefetch.Query.GetNearest() == nil || sparsePrefetch.Query.GetNearest().GetSparse() == nil {
		m.t.Errorf("sparse prefetch query must not be nil and have sparse nearest vector input")
	} else {
		sparseQuery := sparsePrefetch.Query.GetNearest().GetSparse()
		sparseVec := sparseQuery.GetValues()
		sparseIndices := sparseQuery.GetIndices()
		if len(sparseVec) != len(m.expectedSparse) {
			m.t.Errorf("sparse values length mismatch: expected %d, got %d", len(m.expectedSparse), len(sparseVec))
		}
		if len(sparseIndices) != len(m.expectedIndices) {
			m.t.Errorf("sparse indices length mismatch: expected %d, got %d", len(m.expectedIndices), len(sparseIndices))
		}
	}

	valString := &qdrant.Value{Kind: &qdrant.Value_StringValue{StringValue: "test content"}}
	valPage := &qdrant.Value{Kind: &qdrant.Value_DoubleValue{DoubleValue: 1.0}}
	
	return &qdrant.QueryResponse{
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
	req.Header.Set(echo.HeaderContentType, echo.MIMEApplicationJSON)
	w := httptest.NewRecorder()

	e := echo.New()
	c := e.NewContext(req, w)

	err := svc.QueryHandler(c)
	if err != nil {
		t.Fatalf("unexpected error in QueryHandler: %v", err)
	}

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
	provider, err := core.NewBedrockProvider(context.Background(), "eu-central-1", "")
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
