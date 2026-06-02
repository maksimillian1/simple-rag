package core

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/bedrockruntime"
)

// Llama3Request represents the prompt payload for Bedrock Llama 3.2 3B Instruct model
type Llama3Request struct {
	Prompt       string  `json:"prompt"`
	MaxGenLen    int     `json:"max_gen_len,omitempty"`
	Temperature  float64 `json:"temperature,omitempty"`
	TopP         float64 `json:"top_p,omitempty"`
}

// Llama3Response represents the generation response from Bedrock Llama 3.2 3B Instruct model
type Llama3Response struct {
	Generation           string `json:"generation"`
	PromptTokenCount     int    `json:"prompt_token_count"`
	GenerationTokenCount int    `json:"generation_token_count"`
	StopReason           string `json:"stop_reason"`
}

// MockProvider is a local mock provider for test isolation
type MockProvider struct{}

func NewMockProvider() *MockProvider {
	return &MockProvider{}
}

func (m *MockProvider) GenerateAnswer(ctx context.Context, query string, citations []Citation) (string, error) {
	return SynthesizeAnswerPlaceholder(query, citations), nil
}

// BedrockProvider is the production provider using AWS Bedrock Runtime
type BedrockProvider struct {
	client  *bedrockruntime.Client
	modelID string
}

func NewBedrockProvider(ctx context.Context, region string, modelID string) (*BedrockProvider, error) {
	var opts []func(*config.LoadOptions) error
	if region != "" {
		opts = append(opts, config.WithRegion(region))
	}

	// Shield Bedrock from global environmental endpoint overrides (like AWS_ENDPOINT_URL for local SQS)
	os.Setenv("AWS_IGNORE_CONFIGURED_ENDPOINT_URLS", "true")

	cfg, err := config.LoadDefaultConfig(ctx, opts...)
	if err != nil {
		return nil, fmt.Errorf("failed to load AWS config for Bedrock: %w", err)
	}

	client := bedrockruntime.NewFromConfig(cfg)
	return &BedrockProvider{
		client:  client,
		modelID: modelID,
	}, nil
}

func (b *BedrockProvider) GenerateAnswer(ctx context.Context, query string, citations []Citation) (string, error) {
	// If MODEL_ID is not configured, fall back to basic placeholder citation synthesis
	if b.modelID == "" {
		log.Println("[INFO] [bedrock-provider] MODEL_ID is empty. Falling back to local placeholder citation synthesis.")
		return SynthesizeAnswerPlaceholder(query, citations), nil
	}

	if len(citations) == 0 {
		return "I searched the vector database but could not find any direct references to your query. Please make sure you have successfully indexed documents or run the seeder script.", nil
	}

	// Construct Llama 3 prompt compiled with context chunks
	var chunksBuilder strings.Builder
	for i, cit := range citations {
		fmt.Fprintf(&chunksBuilder, "[Chunk %d] Source: %s, Page: %d, Score: %.4f\nContent: %s\n\n", i+1, cit.FileName, cit.PageNumber, cit.Score, cit.TextSnippet)
	}

	prompt := fmt.Sprintf(`<|begin_of_text|><|start_header_id|>system<|end_header_id|>

    You are an elite, concise technical engine. Your task is to answer the user query based on the document chunks provided below.

    CRITICAL INSTRUCTIONS:
    - Directly answer the question in a confident, technical manner.
    - Do not use phrases like "Based on the provided chunks", "Unfortunately, I don't have enough information", or "The text doesn't explicitly state".
    - If a chunk describes a tool's capabilities, features, or deployment steps, state clearly what the technology does based on those actions.
    - Synthesize the details into a coherent definition. Do not say "I don't know" if there are technical features listed.
    - Respond with ONLY the answer. Do not output instructions, prompt tags, or system blocks.<|eot_id|><|start_header_id|>user<|end_header_id|>

    Query: %s

    Document Chunks:
    %s

    Answer:<|eot_id|><|start_header_id|>assistant<|end_header_id|>`, query, chunksBuilder.String())

	reqPayload := Llama3Request{
		Prompt:      prompt,
		MaxGenLen:   512,
		Temperature: 0.5,
		TopP:        0.9,
	}

	bodyBytes, err := json.Marshal(reqPayload)
	if err != nil {
		return "", fmt.Errorf("failed to marshal request payload: %w", err)
	}

	input := &bedrockruntime.InvokeModelInput{
		ModelId:     aws.String(b.modelID),
		ContentType: aws.String("application/json"),
		Accept:      aws.String("application/json"),
		Body:        bodyBytes,
	}

	resp, err := b.client.InvokeModel(ctx, input)
	if err != nil {
		return "", fmt.Errorf("failed to invoke Bedrock model '%s': %w", b.modelID, err)
	}

	var respPayload Llama3Response
	if err := json.Unmarshal(resp.Body, &respPayload); err != nil {
		return "", fmt.Errorf("failed to unmarshal response payload: %w", err)
	}

	return respPayload.Generation, nil
}

// NewLLMProvider constructs the appropriate LLMProvider based on configuration
func NewLLMProvider(ctx context.Context, providerType string, region string, modelID string) (LLMProvider, error) {
	if strings.ToLower(providerType) == "bedrock" {
		return NewBedrockProvider(ctx, region, modelID)
	}
	return NewMockProvider(), nil
}

// SynthesizeAnswerPlaceholder builds a readable bullet point summary from retrieved citations
func SynthesizeAnswerPlaceholder(query string, citations []Citation) string {
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
