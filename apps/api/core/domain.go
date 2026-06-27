package core

import "context"

type Citation struct {
	DocumentID  string  `json:"document_id"`
	FileName    string  `json:"file_name"`
	PageNumber  int     `json:"page_number"`
	Score       float64 `json:"score"`
	TextSnippet string  `json:"text_snippet"`
}

type QueryRequest struct {
	Query                 string   `json:"query"`
	TopK                  int      `json:"top_k"`
	PoolAlpha             *float64 `json:"pool_alpha,omitempty"`
	RrfMergePriorityAlpha *float64 `json:"rrf_merge_priority_alpha,omitempty"`
	RrfK                  int      `json:"rrf_k,omitempty"`
	Dense                 *bool    `json:"dense,omitempty"`
	Sparse                *bool    `json:"sparse,omitempty"`
	Debug                 bool     `json:"debug"`
}

type DebugResult struct {
	ID       interface{}            `json:"id"`
	Score    float64                `json:"score"`
	Text     string                 `json:"text"`
	Metadata map[string]interface{} `json:"metadata"`
}

type DebugBlock struct {
	Results []DebugResult `json:"results"`
	Count   int           `json:"count"`
}

type QueryResponse struct {
	Answer          string      `json:"answer"`
	ExecutionTimeMS int64       `json:"execution_time_ms"`
	Citations       []Citation  `json:"citations"`
	Debug           *DebugBlock `json:"debug,omitempty"`
}

type LLMProvider interface {
	GenerateAnswer(ctx context.Context, query string, citations []Citation) (string, error)
}
