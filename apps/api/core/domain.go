package core

import "context"

// Citation represents a documented vector retrieval source snippet
type Citation struct {
	DocumentID  string  `json:"document_id"`
	FileName    string  `json:"file_name"`
	PageNumber  int     `json:"page_number"`
	Score       float64 `json:"score"`
	TextSnippet string  `json:"text_snippet"`
}

// QueryRequest is the synchronous RAG request schema
type QueryRequest struct {
	Query string  `json:"query"`
	TopK  int     `json:"top_k"`
	Alpha float64 `json:"alpha"`
	Debug bool    `json:"debug"`
}

// DebugResult is a single search result for dashboard compatibility
type DebugResult struct {
	ID       interface{}            `json:"id"`
	Score    float64                `json:"score"`
	Text     string                 `json:"text"`
	Metadata map[string]interface{} `json:"metadata"`
}

// DebugBlock encapsulates all debug insights
type DebugBlock struct {
	Results []DebugResult `json:"results"`
	Count   int           `json:"count"`
}

// QueryResponse is the final generated answer response schema
type QueryResponse struct {
	Answer          string      `json:"answer"`
	ExecutionTimeMS int64       `json:"execution_time_ms"`
	Citations       []Citation  `json:"citations"`
	Debug           *DebugBlock `json:"debug,omitempty"`
}

// LLMProvider is the core interface for response generation
type LLMProvider interface {
	GenerateAnswer(ctx context.Context, query string, citations []Citation) (string, error)
}
