# Baseline — Metrics

Refs are cited from outside this execution by path: `00-baseline/M1`.

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | idle spend by service, over the idle window | Cost Explorer · daily granularity · `TAG:feature=simple-rag` present | ⟨confirmed YYYY-MM-DD⟩ | every floor line resolves to a row of this → K1 · K3 |
| M2 | share of idle spend arriving with no attribution tag | same source, tag absent | ⟨confirmed YYYY-MM-DD⟩ | gate: under 5 %, resolved before the split is trusted → K3 |
| M3 | node inventory during the idle window | `kube_node_labels` | ⟨confirmed YYYY-MM-DD⟩ | proof of idleness: `apps-compute` at zero for the whole window. Selector `label_karpenter_sh_nodepool` — unfiltered it counts the Qdrant node as elastic capacity |
| R4 | Qdrant resident memory at teardown | `kubectl top pod`, once, at ⟨moment⟩ · ⟨who⟩ | active | sizes the instance class. A time series of it would not change the instance → K4 |
| D5 | Block C | `A + B` | active | arithmetic over the floor blocks; carries no line and no fixed/variable attribute |
| D6 | Qdrant vector memory | `dims × bytes_per_dim × points × (1 + index overhead)` | active | given, not finding → K4 |
| E7 | always-on alternative for the floor | ⟨basis⟩ vs Block B | active | the reference value §2 Floor is judged against → K6 |

Name confirmation is the gate: a string copied from chart documentation returns NO DATA on a
healthy endpoint, and the failure reads as a missing scrape target.

## Not observed here, deliberately

| What | Why it is not needed |
| :--- | :--- |
| Qdrant `points_count` as a series | read once per run over REST in `01-ingestion` (`R13`); a series answers no question this report asks |
| Karpenter controller metrics | no claim in v1.0 depends on interruption counts; `01-ingestion/R11` records them per point |
| Go API request metrics | no query-path run consumes them in v1.0 → report Coverage |
| Node warm-up sub-phases — provisioning, image pull, runtime init | report §3.4 needs the overhead share, not its attribution |

Instrumentation without a consumer generates work rather than evidence. It is added with the
run that needs it.
