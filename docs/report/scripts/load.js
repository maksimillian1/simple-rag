// load.js — generator for 02-inference. Invoked by run-inference-point.py as:
//   k6 run --tag point={run} ./load.js
// with BASE_URL, TARGET_RATE and DURATION set in the environment
// (run-inference-point.py GENERATOR_ENV). --tag is a k6 CLI flag, not read
// here. Duration comes through DURATION rather than the k6 --duration flag:
// once a `scenarios` block is present, k6 ignores the CLI/top-level
// `duration` option entirely, so the two must not drift apart.
//
// Open-loop: constant-arrival-rate schedules a new iteration every 1/rate
// seconds regardless of how long the previous one took, so TARGET_RATE is
// the actual offered rate, not an approximation via VU count. A VU pool is
// still needed to hold requests that are in flight — sized off MOCK_DELAY_MS
// (Little's Law: concurrent in-flight ~= rate * request duration), with
// headroom in maxVUs in case real latency runs past the mock delay.
//
// Served rate, errors and latency are read from Prometheus, never from k6's
// own output — see 02-inference/metrics.md M1-M3.

import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const TARGET_RATE = parseFloat(__ENV.TARGET_RATE || '1');
const DURATION = __ENV.DURATION || '1m';

// Frozen in 00-baseline §2 Configuration freeze: "Generation — stubbed at the
// frozen delay. No run in this report calls Bedrock." Without mock_delay_ms
// in the body, apps/api/search/search.go falls through to a real
// s.LLM.GenerateAnswer() call — every point would bill real Bedrock usage and
// its latency would depend on Bedrock rather than the frozen 2000ms constant
// every other 02-inference figure is read against.
const MOCK_DELAY_MS = parseInt(__ENV.MOCK_DELAY_MS || '2000', 10);

// Expected wall time per request: the mock delay plus slack for network,
// Qdrant, and TEI round trips. Under-sizing this under-sizes preAllocatedVUs,
// which stalls arrivals (k6 logs "no more VUs available") rather than
// missing the target rate silently.
const EXPECTED_REQUEST_S = MOCK_DELAY_MS / 1000 + 0.5;
const PRE_ALLOCATED_VUS = Math.max(10, Math.ceil(TARGET_RATE * EXPECTED_REQUEST_S));
const MAX_VUS = PRE_ALLOCATED_VUS * 2;

export const options = {
  scenarios: {
    constant_load: {
      executor: 'constant-arrival-rate',
      rate: TARGET_RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: PRE_ALLOCATED_VUS,
      maxVUs: MAX_VUS,
    },
  },
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
  const payload = JSON.stringify({ query, top_k: 5, mock_delay_ms: MOCK_DELAY_MS });
  const params = {
    headers: { 'Content-Type': 'application/json' },
    tags: { name: 'query' },
  };

  const res = http.post(`${BASE_URL}/api/v1/query`, payload, params);
  check(res, { 'status is 200': (r) => r.status === 200 });
}
