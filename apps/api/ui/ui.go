package ui

import (
	_ "embed"
	"net/http"
	"strings"
)

//go:embed templates/index.html
var indexHTML string

// Service coordinates dashboard views and assets
type Service struct {
	Environment string
	Collection  string
}

// NewService instantiates a new UI Service
func NewService(environment, collection string) *Service {
	return &Service{
		Environment: environment,
		Collection:  collection,
	}
}

// Handler serves the embedded dashboard HTML resolving configuration mappings
func (s *Service) Handler(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")

	// Render dashboard embedding current environment details dynamically
	html := strings.Replace(indexHTML, "{{.Environment}}", s.Environment, -1)
	html = strings.Replace(html, "{{.Collection}}", s.Collection, -1)
	w.Write([]byte(html))
}
