package ui

import (
	_ "embed"
	"net/http"
	"strings"

	"github.com/labstack/echo/v4"
)

//go:embed templates/index.html
var indexHTML string

type Service struct {
	Environment string
	Collection  string
}

func NewService(environment, collection string) *Service {
	return &Service{
		Environment: environment,
		Collection:  collection,
	}
}

func (s *Service) Handler(c echo.Context) error {
	html := strings.Replace(indexHTML, "{{.Environment}}", s.Environment, -1)
	html = strings.Replace(html, "{{.Collection}}", s.Collection, -1)
	return c.HTML(http.StatusOK, html)
}
