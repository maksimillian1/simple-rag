// load.js — generator for 02-inference. Invoked by run-inference-point.py as:
//   k6 run --duration {duration} --tag point={run} ./load.js
// with BASE_URL and TARGET_RATE set in the environment (run-inference-point.py
// GENERATOR_ENV). --duration and --tag are k6 CLI flags, not read here.
//
// Approximation: one VU issues roughly one request per second (request +
// sleep(1)), so VU count approximates the offered rate in req/s. This is a
// closed-loop generator — a VU blocked on a slow response delays its next
// request rather than queuing on schedule. For a strict open-loop offered
// rate (recommended once this needs to be precise), replace `options` with a
// `constant-arrival-rate` scenario driven by TARGET_RATE.
//
// Served rate, errors and latency are read from Prometheus, never from k6's
// own output — see 02-inference/metrics.md M1-M3.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const TARGET_RATE = parseFloat(__ENV.TARGET_RATE || '1');

export const options = {
  vus: Math.max(1, Math.ceil(TARGET_RATE)),
  duration: '1m', // overridden by the --duration flag on the k6 CLI
};

// Sample queries against the frozen corpus. Swap for a fixed set drawn from
// the actual ingested documents before a point is trusted.
const QUERIES = [
  'How does retrieval augmented generation reduce hallucination?',
  'What is the difference between dense and sparse embeddings?',
  'Summarize the ingestion pipeline for uploaded documents.',
  'What does the chunker service do before indexing?',
  'How is query latency measured for the search API?',
];

export default function () {
  const query = QUERIES[Math.floor(Math.random() * QUERIES.length)];
  const payload = JSON.stringify({ query, top_k: 5 });
  const params = {
    headers: { 'Content-Type': 'application/json' },
    tags: { name: 'query' },
  };

  const res = http.post(`${BASE_URL}/api/v1/query`, payload, params);
  check(res, { 'status is 200': (r) => r.status === 200 });

  sleep(1);
}
