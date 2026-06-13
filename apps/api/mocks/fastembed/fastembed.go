package fastembed

import "context"

type ModelName string

const (
	SPLADE_PP_ED8R ModelName = "SPLADE_PP_ED8R"
)

type Option func(*options)

type options struct {
	model ModelName
}

func WithModel(model ModelName) Option {
	return func(o *options) {
		o.model = model
	}
}

type SparseEmbedding struct {
	Indices []uint32
	Values  []float32
}

type SparseEmbeddingModel struct {
	model ModelName
}

func NewSparseEmbeddingModel(opts ...Option) (*SparseEmbeddingModel, error) {
	o := &options{}
	for _, opt := range opts {
		opt(o)
	}
	return &SparseEmbeddingModel{model: o.model}, nil
}

func (m *SparseEmbeddingModel) Embed(ctx context.Context, texts []string) ([]SparseEmbedding, error) {
	results := make([]SparseEmbedding, len(texts))
	for i := range texts {
		results[i] = SparseEmbedding{
			Indices: []uint32{100, 200, 300},
			Values:  []float32{0.5, 0.3, 0.2},
		}
	}
	return results, nil
}
