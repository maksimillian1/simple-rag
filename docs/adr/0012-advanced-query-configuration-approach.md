# 12: Advanced Query Configuration Approach

Date: 2026-06-27

## Status
Accepted

## Context
During the implementation of the Two-Stage Hybrid Retrieval, it was noted that configurations such as `poolAlpha`—which balances the weighting between dense and sparse vector retrieval in hybrid mode—can be set to extreme values (e.g., `0.0` or `1.0`). Such values can result in a `0` prefetch limit for one side of the retrieval pipeline, effectively negating the "hybrid" nature of the query and potentially causing unexpected behavior in downstream algorithms like Reciprocal Rank Fusion (RRF).

It was proposed to introduce code-level clamping and validation to enforce a minimum prefetch limit per enabled mode, preventing developers from configuring parameters that contradict the semantic intent of "hybrid" mode.

## Decision
Reject the introduction of code-level clamping, validation guardrails, and artificial limits for query configuration parameters. 

Instead, we adopt a **Documentation-First Configuration** approach:
* We will document the mathematical and behavioral consequences of setting values like `poolAlpha` in the README.
* If a configuration effectively zeroes out the dense or sparse pipeline (e.g., `poolAlpha=0.0`), the system will execute exactly as configured.
* We allow developers to intentionally (or accidentally) misuse the configuration.

## Justification
This decision strictly adheres to our **Zero-Abstraction Policy** and **Production-Ready Mandate**:
1. **Zero Bloat:** Adding defensive code (clamping bounds, minimum enforcement rules, type coercions) adds unnecessary branching and cognitive load to the core execution path.
2. **Raw Control:** By avoiding opinionated guardrails, we allow advanced use cases where a developer might *want* to temporarily force a hybrid query to act as a pure sparse or dense query without changing the underlying endpoint or API structure.
3. **Transparency over Magic:** If a configuration is invalid, the resulting behavior (or failure) is predictable and traceable, rather than being mysteriously corrected by hidden clamping logic.

## Consequences

### What becomes easier:
* **Code Simplicity:** The Go query layer (`apps/api/`) remains extremely thin, clean, and highly performant with fewer branches and runtime checks.
* **Flexibility:** Advanced users have unbounded control over the retrieval behavior.

### What becomes more difficult:
* **Developer Experience:** Integrators must read and understand the documentation. The API will not "save" them from configuring a mathematically unsound query (e.g., setting hybrid parameters that produce zero results).
