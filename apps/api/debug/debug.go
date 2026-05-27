package debug

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type Service struct {
	Environment string
	SQSQueueURL string
}

func NewService(environment, sqsQueueURL string) *Service {
	return &Service{
		Environment: environment,
		SQSQueueURL: sqsQueueURL,
	}
}

func (s *Service) SeedHandler(w http.ResponseWriter, r *http.Request) {
	if s.Environment != "dev" {
		http.Error(w, "Forbidden in non-dev environment", http.StatusForbidden)
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}

	log.Println("[INFO] [debug] Seeding database via seed.sh...")

	// Find seed.sh path dynamically
	dir, err := os.Getwd()
	if err != nil {
		http.Error(w, "Internal Server Error: "+err.Error(), http.StatusInternalServerError)
		return
	}
	var seedPath string
	for {
		target := filepath.Join(dir, "apps", "api", "seed.sh")
		if _, err := os.Stat(target); err == nil {
			seedPath = target
			break
		}
		targetInDir := filepath.Join(dir, "seed.sh")
		if _, err := os.Stat(targetInDir); err == nil {
			seedPath = targetInDir
			break
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}

	if seedPath == "" {
		http.Error(w, "seed.sh not found", http.StatusNotFound)
		return
	}

	log.Printf("[INFO] [debug] Running seed script at: %s", seedPath)
	cmd := exec.Command("bash", seedPath)
	cmd.Dir = filepath.Dir(seedPath)

	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &out

	err = cmd.Run()
	outputStr := out.String()
	if err != nil {
		log.Printf("[ERROR] [debug] Seeding failed: %v, output: %s", err, outputStr)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{
			"status": "error",
			"output": outputStr,
			"error":  err.Error(),
		})
		return
	}

	log.Println("[INFO] [debug] Seeding completed successfully!")
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{
		"status": "ok",
		"output": outputStr,
	})
}

func (s *Service) IndexHandler(w http.ResponseWriter, r *http.Request) {
	if s.Environment != "dev" {
		http.Error(w, "Forbidden in non-dev environment", http.StatusForbidden)
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}

	type IndexRequest struct {
		Text string `json:"text"`
	}

	var req IndexRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid Request Body: "+err.Error(), http.StatusBadRequest)
		return
	}

	reqText := strings.TrimSpace(req.Text)
	if reqText == "" {
		http.Error(w, "Text content cannot be empty", http.StatusBadRequest)
		return
	}

	// Prepare standard payload that Indexer app expects in Stage 2 indexing
	payload := map[string]interface{}{
		"file_name": "manual_web_input",
		"metadata": map[string]interface{}{
			"source":    "control_panel_manual_input",
			"timestamp": time.Now().Format(time.RFC3339),
		},
		"chunks": []map[string]interface{}{
			{
				"text":  reqText,
				"index": 0,
			},
		},
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		http.Error(w, "Failed to marshal payload", http.StatusInternalServerError)
		return
	}

	log.Printf("[INFO] [debug] Sending manual chunk payload to SQS Stage 2: %s", string(payloadBytes))

	// Form URL encoded SQS query message payload
	formData := url.Values{}
	formData.Set("Action", "SendMessage")
	formData.Set("MessageBody", string(payloadBytes))

	client := http.Client{Timeout: 5 * time.Second}
	resp, err := client.PostForm(s.SQSQueueURL, formData)
	if err != nil {
		log.Printf("[ERROR] [debug] Failed to forward manual chunk message to SQS: %v", err)
		http.Error(w, "Failed to contact SQS Queue Service: "+err.Error(), http.StatusServiceUnavailable)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		log.Printf("[ERROR] [debug] SQS returned error code %d: %s", resp.StatusCode, string(bodyBytes))
		http.Error(w, "SQS queue returned error response", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{
		"status":  "ok",
		"message": "Manual chunk successfully sent to SQS queue. The continuous indexer worker will pull and process it in a few seconds.",
	})
}
