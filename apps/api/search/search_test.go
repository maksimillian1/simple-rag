package search

import (
	"context"
	"math"
	"strings"
	"testing"

	"github.com/maksimillian1/simple-rag/apps/api/core"
)

func TestComputeSparseVector(t *testing.T) {
	text := "Financial growth growth Q1"

	// Expected token count and weights from Python:
	// words: ["financial", "growth", "growth", "q1"] -> total 4 words
	// counts: {"financial": 1, "growth": 2, "q1": 1}
	// financial: index = 306840486, value = 0.25
	// growth: index = 152765084, value = 0.50
	// q1: index = 18153635, value = 0.25
	// Sorted by index ascending:
	// 18153635 (0.25), 152765084 (0.50), 306840486 (0.25)

	res := computeSparseVector(text)

	if len(res.Indices) != 3 {
		t.Fatalf("expected 3 indices, got %d", len(res.Indices))
	}
	if len(res.Values) != 3 {
		t.Fatalf("expected 3 values, got %d", len(res.Values))
	}

	expectedIndices := []uint32{18153635, 152765084, 306840486}
	expectedValues := []float64{0.25, 0.50, 0.25}

	for i := range expectedIndices {
		if res.Indices[i] != expectedIndices[i] {
			t.Errorf("at index %d, expected index %d, got %d", i, expectedIndices[i], res.Indices[i])
		}
		if math.Abs(res.Values[i]-expectedValues[i]) > 1e-6 {
			t.Errorf("at index %d, expected value %f, got %f", i, expectedValues[i], res.Values[i])
		}
	}
}

func TestComputeSparseVectorEmpty(t *testing.T) {
	text := "   "
	res := computeSparseVector(text)
	if len(res.Indices) != 0 || len(res.Values) != 0 {
		t.Errorf("expected empty sparse vector, got indices: %v, values: %v", res.Indices, res.Values)
	}
}

func TestComputeTermCountPenalty(t *testing.T) {
	// Case 1: No match
	penaltyNoMatch := computeTermCountPenalty("Financial statement text", "growth")
	if penaltyNoMatch != 1.0 {
		t.Errorf("expected penalty to be 1.0 for no matching query words, got %f", penaltyNoMatch)
	}

	// Case 2: 1 match
	// count = 1 -> 1 / log10(1 + 10) = 1 / log10(11) ≈ 1 / 1.04139 ≈ 0.96025
	penaltyOneMatch := computeTermCountPenalty("Financial growth text", "growth")
	expectedOne := 1.0 / math.Log10(11.0)
	if math.Abs(penaltyOneMatch-expectedOne) > 1e-6 {
		t.Errorf("expected penalty %f, got %f", expectedOne, penaltyOneMatch)
	}

	// Case 3: 3 matches
	// count = 3 -> 1 / log10(3 + 10) = 1 / log10(13) ≈ 1 / 1.11394 ≈ 0.89771
	penaltyThreeMatches := computeTermCountPenalty("growth growth financial growth text", "growth")
	expectedThree := 1.0 / math.Log10(13.0)
	if math.Abs(penaltyThreeMatches-expectedThree) > 1e-6 {
		t.Errorf("expected penalty %f, got %f", expectedThree, penaltyThreeMatches)
	}

	// Case 4: Multiple query words match
	// query: "growth audit", text: "growth audit audit document"
	// query words: ["growth", "audit"]
	// text counts: growth=1, audit=2
	// total = 3 -> 1 / log10(3 + 10) = 1 / log10(13)
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

	// k = 60.0
	// Point B: in dense at rank 2 (index 1), in sparse at rank 1 (index 0)
	// Score_B = 1/(60+2) + 1/(60+1) = 1/62 + 1/61 ≈ 0.016129 + 0.016393 = 0.032522
	// Point A: in dense at rank 1 (index 0)
	// Score_A = 1/(60+1) = 1/61 ≈ 0.016393
	// Point C: in sparse at rank 2 (index 1)
	// Score_C = 1/(60+2) = 1/62 ≈ 0.016129

	results := performRRF(densePoints, sparsePoints, 60.0)

	if len(results) != 3 {
		t.Fatalf("expected 3 merged points, got %d", len(results))
	}

	// Top point should be Point B
	if results[0].ID != "point_B" {
		t.Errorf("expected top point to be point_B, got %v", results[0].ID)
	}
	expectedB := 1.0/62.0 + 1.0/61.0
	if math.Abs(results[0].Score-expectedB) > 1e-6 {
		t.Errorf("expected Point B score %f, got %f", expectedB, results[0].Score)
	}

	// Second point should be Point A
	if results[1].ID != "point_A" {
		t.Errorf("expected second point to be point_A, got %v", results[1].ID)
	}
	expectedA := 1.0 / 61.0
	if math.Abs(results[1].Score-expectedA) > 1e-6 {
		t.Errorf("expected Point A score %f, got %f", expectedA, results[1].Score)
	}

	// Third point should be Point C
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
	// Initialize BedrockProvider with empty modelID
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
