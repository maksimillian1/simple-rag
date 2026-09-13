# report.md — open decisions

## Business call, left blank on purpose

**§1 Verdict** (ship / ship with guardrails / do not ship) is not filled in, because it is a
business decision. The technical read: the system is cheap to run and has headroom on both paths
at every volume tested. Three gaps stand between that and a confident verdict: no Fargate
comparison (`01-ingestion/D29`), no contention pass (`02-inference` §3.8), and no real-Bedrock
cost calibration (`E18` is derived, never measured). Each execution's `questionnaire.md` asks
whether its gap is worth closing before the verdict.

## Config drift: live cluster settings don't match this report's findings

**Ingestion `maxReplicaCount` is live at 10; the sweet spot found is 25** (`01-ingestion` §3,
`deploy/k8s/apps/{chunker,indexer}/scaledjob.yaml`). Raise it to match, or is 10 intentional for a
reason this report never captured?

**`tei-embeddings-scaler` `maxReplicaCount` (30) is fully used at the highest rate tested**
(`r1000`, 30/30 replicas, `02-inference` §3). Above 1000 req/s there is no room to scale under the
current cap. Raising the cap runs into this AWS account's Spot vCPU quota (`L-34B43A08` = 256) at
about 35-40 replicas anyway. Request a quota increase, or is 1000 req/s beyond any traffic this
deployment will see?

## Housekeeping

**`terraform/budgets.tf` doesn't exist.** The §5 Guardrails table names it as the place that
enforces the budget alarm ($598/month recommended = Block B × 1.4). Nothing enforces it today.
Write the file, or is a budget alarm not wanted at this project's scale?

Per-execution items are in `executions/{00-baseline,01-ingestion,02-inference}/questionnaire.md`:
a `methodology.md` that two executions cite and nobody wrote, a duplicate-PVC pattern, and whether
the contention pass and the Fargate comparison justify re-provisioning a cluster.
