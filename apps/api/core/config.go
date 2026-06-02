package core

import (
	"bufio"
	"log"
	"os"
	"path/filepath"
	"strings"
)

// Config represents all central environment parameters
type Config struct {
	Port                 string
	QdrantURL            string
	Collection           string
	EmbeddingModelTeiURL string
	Environment          string
	SQSQueueURL          string
	LLMProvider          string
	AwsRegion            string
	ModelID              string
}

// LoadEnv walks up from the current working directory to locate and parse the nearest .env file
func LoadEnv() {
	dir, err := os.Getwd()
	if err != nil {
		return
	}
	envFile := ".env"
	if appEnv := os.Getenv("APP_ENV"); appEnv != "" {
		envFile = ".env." + appEnv
	}
	for {
		envPath := filepath.Join(dir, envFile)
		if _, err := os.Stat(envPath); err == nil {
			file, err := os.Open(envPath)
			if err != nil {
				return
			}
			defer file.Close()
			scanner := bufio.NewScanner(file)
			for scanner.Scan() {
				line := strings.TrimSpace(scanner.Text())
				if line == "" || strings.HasPrefix(line, "#") {
					continue
				}
				parts := strings.SplitN(line, "=", 2)
				if len(parts) == 2 {
					key := strings.TrimSpace(parts[0])
					val := strings.TrimSpace(parts[1])
					if strings.HasPrefix(val, "\"") && strings.HasSuffix(val, "\"") {
						val = val[1 : len(val)-1]
					} else if strings.HasPrefix(val, "'") && strings.HasSuffix(val, "'") {
						val = val[1 : len(val)-1]
					}
					os.Setenv(key, val)
				}
			}
			log.Printf("[INFO] Loaded environment variables from %s", envPath)
			return
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
}

// GetEnv resolves an environment variable or falls back to a default value
func GetEnv(key, defaultVal string) string {
	if val, exists := os.LookupEnv(key); exists {
		return val
	}
	return defaultVal
}

// LoadConfig initializes the environment configurations and parses them with sensible defaults
func LoadConfig() Config {
	LoadEnv()
	return Config{
		Port:                 GetEnv("PORT", "8080"),
		QdrantURL:            GetEnv("QDRANT_URL", "http://localhost:6333"),
		Collection:           GetEnv("COLLECTION_NAME", "demo_collection"),
		EmbeddingModelTeiURL: GetEnv("EMBEDDING_MODEL_TEI_URL", "http://localhost:8081"),
		Environment:          GetEnv("ENVIRONMENT", "production"),
		SQSQueueURL:          GetEnv("AWS_SQS_STAGE_2_URL", "http://localhost:9324/000000000000/stage-2-indexing"),
		LLMProvider:          GetEnv("LLM_PROVIDER", "mock"),
		AwsRegion:            GetEnv("AWS_DEFAULT_REGION", "us-east-1"),
		ModelID:              GetEnv("MODEL_ID", ""),
	}
}
