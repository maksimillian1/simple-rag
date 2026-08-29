# 00 · Baseline

| Field | Value |
| :--- | :--- |
| Why this execution exists | the system at rest — what `01-ingestion` and `02-inference` inherit and never re-measure |
| Produces | frozen configuration · the denominator · the price basis · the metric register · the floor |
| Expected *(recorded ⟨date⟩)* | Block B is dominated by the Qdrant On-Demand node and its gp3 volume; everything else in B is under ⟨10⟩ % |
| Status | ⟨planning · capturing · closed⟩ |
| Revision | v1.0 · supersedes — |
| Frozen | ⟨date⟩ · commit ⟨sha⟩ |
| Optional files | `./concepts.md` · `./metrics.md` — the E register |

> Values here · mechanisms in `./concepts.md` as `M⟨n⟩` · kit rules in `methodology.md`,
> cited and never restated.

---

# 1 · Plan

## Preconditions for every execution downstream

| # | Check | Blocks | Done |
| :--- | :--- | :--- | :--- |
| 1 | ServiceMonitors for TEI, Qdrant, Karpenter, Go API — names copied off the live endpoint into `./metrics.md`, never from chart docs | E20 · E21 · E30 → report §3.5 Tier 2 | |
| 2 | Every required ref returns data under the selector `01-ingestion` will use → `./metrics.md` filtering table | every execution | |
| 3 | Cost attribution active in Terraform, not the console; Karpenter-created nodes carry the tag | floor · every $ figure | |
| 4 | Prometheus retention ⟨3 d⟩ recorded — shorter than any campaign, so export after every point | every execution | |
| 5 | §3 Constants frozen by name and date · `run-point.py` dry run clean | comparability | |

Row 1 is the only one that gates a *claim* rather than the campaign → M5.

## Idle window rule

| Field | Value |
| :--- | :--- |
| Opens | corpus in place, S3 event notification disabled — decided before the window opens |
| Closes | a full daily cycle later, aligned to the billing backend's granularity → M1 |
| Invalidated by | one execution point falling inside it · any human activity in the cluster |
| Stays on | ArgoCD reconciliation, Karpenter, Cilium, the monitoring stack — that is floor → M2 |
| Evidence | `./data/idle-⟨YYYY-MM-DD⟩.csv` — exported, never asserted |

## What is captured here and cannot be captured later

| Constant | File | Why not later |
| :--- | :--- | :--- |
| Price basis | `./data/price-⟨YYYY-MM-DD⟩.⟨ext⟩` | on-list rates move; anything negotiated appears in no public list |
| Corpus profile | `./data/corpus-profile.txt` | the bucket can be overwritten and the count is not re-derivable from the report |
| Cluster identity | `./data/identity-⟨YYYY-MM-DD⟩.txt` | image digests, chart revisions and AMIs move under you |
| Proof of idleness | `./data/idle-⟨YYYY-MM-DD⟩.csv` | the billing backend does not record what was running |

## What this execution owes the report

| Report section | Expected to produce |
| :--- | :--- |
| §2 Workload contract | unit of work · corpus profile · applicability |
| §4.1 Floor | A / B / C split, line by line |
| §4.3–4.4 | the price basis those two sections compute against |
| Coverage | which components are observable, and which deliberately are not |

---

# 2 · Journal

| Event | Date UTC | Commit | Outcome |
| :--- | :--- | :--- | :--- |
| Constants frozen | | | |
| Corpus profiled | | | |
| Prices captured | | | |
| ServiceMonitors landed | | | ⟨which of E20 · E21 · E30⟩ |
| Idle window | ⟨open⟩ → ⟨close⟩ | | billing data available ⟨date⟩ · untagged spend resolved ⟨date⟩ → M3 |

| Anomaly | Rule applied | Decision |
| :--- | :--- | :--- |
| | | |

---

# 3 · Results

| Block | Present | Feeds |
| :--- | :--- | :--- |
| Constants | yes | report §2 · both executions |
| Metrics — register | yes, in `./metrics.md` | both executions |
| Metrics — figures | yes | report §4.1 · §4.3 |
| Applicability | yes | report §2 |
| Matrix · Saturation · Guardrails | no | no axis, no load |
| Routing · Open · Retro | yes | |

---

## Constants

### Configuration freeze

| Parameter | Value | Where it is set | Why it must be frozen |
| :--- | :--- | :--- | :--- |
| `apps-compute` instance type | ⟨⟩ | Karpenter NodePool | pinning it makes `$/run` a product, not a sum over types → `01-ingestion` M4 |
| chunker requests / limits | ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/chunker` | sets worker packing density → `01-ingestion` M2 |
| indexer requests / limits | ⟨cpu⟩ · ⟨mem⟩ | same | as above · 2 GB hard limit is the OOM guardrail under test |
| TEI replicas | ⟨n⟩ | `deploy/k8s/apps/tei` | a moving replica count makes Tier 2 unattributable |
| Qdrant collection config | ⟨SQ on · dims 384 · sparse on⟩ | Helm values | changing it changes both write cost and RAM → M4 |
| `consolidateAfter` | 30 s | `apps-compute` NodePool | inside the run window by construction → `01-ingestion` M1 |
| Image digests | chunker `⟨sha⟩` · indexer `⟨sha⟩` | | the one thing that must not move while the config commit does |

### Input fixture — the denominator

| Field | Value |
| :--- | :--- |
| Source · snapshot | ⟨bucket / prefix⟩ · frozen ⟨date⟩ |
| **Exact document count** | ⟨n⟩ |
| Distribution | median ⟨⟩ pages · p95 ⟨⟩ · total ⟨⟩ MB · formats ⟨pdf / md / txt split⟩ |
| Unit of work | one source document, done when its last chunk is upserted and counted in Qdrant `points_count` |
| Frozen | ⟨date⟩ · `./data/corpus-profile.txt` |

### Price basis

| Field | Value |
| :--- | :--- |
| File | `./data/price-⟨YYYY-MM-DD⟩.⟨ext⟩` |
| Rate type | ⟨list · Savings Plan · EDP⟩ |
| Region · currency | ⟨eu-central-1⟩ · USD |
| Covers | EC2 On-Demand and Spot by type · EBS gp3 · EKS control plane · Fargate vCPU/GB · NAT hourly and per-GB · S3 storage and requests · SQS requests · Bedrock per 1K tokens |
| Spot basis | ⟨historical average over ⟨window⟩, not the instantaneous quote⟩ |

---

## Metrics — figures

> The register — `E⟨n⟩` names, statuses, required selectors, deliberately-not-observable —
> is in `./metrics.md`. This block holds only what the report cites as a number.

### Reaches zero

| Component | Scales on | Floor | Ceiling | Zero on idle |
| :--- | :--- | :--- | :--- | :--- |
| chunker · indexer | SQS depth (KEDA ScaledJob) | 0 | N, swept in `01-ingestion` | yes |
| `apps-compute` nodes | pending pods (Karpenter) | 0 | quota | yes |
| TEI | ⟨KEDA · fixed⟩ | ⟨n⟩ | ⟨⟩ | ⟨no — baseline replica is Block B⟩ |
| Go API | ⟨⟩ | ⟨n⟩ | ⟨⟩ | no |
| Qdrant | not autoscaled | 1 node + gp3 | — | **no — the dominant Block B line** |
| Monitoring stack | not autoscaled | core node group | — | no — Block A → M2 |

### Floor — cost with the system running and no load

| Block | What it is | $/month | Source |
| :--- | :--- | :--- | :--- |
| A | shared platform — exists without this feature | ⟨⟩ | measured |
| **B** | **feature-dedicated — disappears with it. The headline** | ⟨⟩ | measured |
| C | standalone — A + B | ⟨⟩ | derived |

| Line | Block | $/month | Billed | Source |
| :--- | :--- | :--- | :--- | :--- |
| EKS control plane | A | ⟨73⟩ | regardless of traffic | derived from price basis |
| `core-on-demand` node group | A | ⟨⟩ | regardless | measured |
| Karpenter on Fargate | A | ⟨⟩ | regardless | measured |
| NAT gateway — hourly | A | ⟨⟩ | regardless | derived |
| NAT gateway — per GB | A | ⟨⟩ | per unit of data moved | measured |
| Monitoring stack — Prometheus, Loki, Grafana, EBS | A | ⟨⟩ | regardless | measured → M2 |
| Qdrant node — On-Demand | **B** | ⟨⟩ | regardless | measured |
| Qdrant gp3 volume | **B** | ⟨⟩ | regardless | measured |
| TEI baseline replica | **B** | ⟨⟩ | regardless | measured |
| Go API replica | **B** | ⟨⟩ | regardless | measured |
| S3 — corpus at rest | **B** | ⟨⟩ | regardless | measured |
| SQS — idle | **B** | ⟨0⟩ | per request | measured |

| Field | Value |
| :--- | :--- |
| Reference value | ⟨always-on alternative⟩ · the article's published idle claim → M6 |
| Never divided by | an assumed number of tenant features — that divisor is arbitrary → M2 |
| Raw data | `./data/idle-⟨YYYY-MM-DD⟩.csv` |

### Derived

| Figure | Formula | Inputs | Value |
| :--- | :--- | :--- | :--- |
| Block C | `A + B` | floor lines | ⟨⟩ |
| Qdrant vector memory | `dims × bytes_per_dim × points × (1 + index overhead)` | Constants · corpus profile | ⟨⟩ → M4 |
| Amortization lower bound | volume at which `B ÷ V` drops below the marginal term | Block B · `01-ingestion` marginal | ⟨computed at report time⟩ |

---

## Applicability

| Dimension | Figures hold for | Re-measure outside |
| :--- | :--- | :--- |
| Platform | ⟨region⟩ · EKS ⟨version⟩ · Karpenter ⟨version⟩ · pinned instance types | any node-type change |
| Scale | one Qdrant node · collection under ⟨n⟩ points | sharded Qdrant |
| Input | the frozen corpus profile — Constants | a different format mix, especially PDF share |
| Environment | single-tenant cluster, no co-tenant load during any window | shared cluster |
| Commercial | rate type and date — Constants | after any rate change |

Deliberately outside: multi-region, GPU inference, managed vector SaaS.

---

## Routing

| Result | Destination | Applied |
| :--- | :--- | :--- |
| Constants — unit of work, corpus profile | report §2 | |
| Applicability | report §2 Envelope | |
| Floor A / B / C + lines | report §4.1 | |
| Price basis | report §4.3–4.4, computed there | |
| Register status of E20 · E21 · E30 | report Coverage, and out-of-scope if still pending at close | |

| Gate condition | Met |
| :--- | :--- |
| §1 rows 2–5 green — row 1 is a claim gate, not a campaign gate | |
| Idle window closed, proof exported, untagged spend resolved | |
| Every Open item resolved or carried into the report as declared scope | |
| Date · by | ⟨date⟩ |

---

## Open

| Item | What it invalidates if wrong | Resolved |
| :--- | :--- | :--- |
| NAT egress series separates cluster-internal from NAT-bound traffic | the NAT line of the marginal decomposition, silently | |
| Untagged spend under ⟨5⟩ % of the idle bill | the A / B split, not the total | |
| Spot historical average is representative of the run window | every `$/run` in `01-ingestion` | |

---

## Retro

| Field | Value |
| :--- | :--- |
| Expectation | ⟨held · inverted — which line actually dominates B⟩ |
| Cost against estimate | |
| What should have been checked earlier | |
| What belongs back in the kit | |
